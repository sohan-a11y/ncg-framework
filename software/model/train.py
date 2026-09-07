"""Training pipeline for NCG Transformer model."""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from ncg.config import TrainingConfig
from torch.cuda.amp import GradScaler, autocast
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR, LinearLR, SequentialLR

from .model import NCGTransformer, create_model
from .tokenizer import MetadataTokenizer, PasswordTokenizer

logger = logging.getLogger(__name__)


class NCGTrainer:
    """Trainer for NCG Transformer model."""

    def __init__(
        self,
        model: NCGTransformer,
        config: TrainingConfig,
        device: torch.device,
        tokenizer: PasswordTokenizer,
        metadata_tokenizer: MetadataTokenizer | None = None,
    ):
        self.model = model
        self.config = config
        self.device = device
        self.tokenizer = tokenizer
        # Present only when the dataset carries real breach-context metadata
        # (organization/year/known_leaks/...); its vocab is persisted in the
        # checkpoint so inference can decode the same context later.
        self.metadata_tokenizer = metadata_tokenizer

        self.model.to(device)

        # Optimizer
        self.optimizer = AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
            betas=(0.9, 0.95),
            eps=1e-8,
        )

        # Mixed precision
        self.scaler = GradScaler(enabled=config.mixed_precision)
        self.mixed_precision = config.mixed_precision

        # Gradient clipping
        self.gradient_clip = config.gradient_clip

        # Quantization aware training: actually engage INT4 fake-quantization
        # in the model's forward pass (previously this flag was stored but
        # never applied, so "quantization_aware=True" trained a plain FP32
        # model). See QuantizedLinear.forward / NCGTransformer.set_qat_enabled.
        self.quantization_aware = config.quantization_aware
        self.model.set_qat_enabled(self.quantization_aware)

        # Distillation
        self.distillation = config.distillation
        self.teacher_model: nn.Module | None = None
        if self.distillation and config.teacher_model_path:
            self._load_teacher_model(config.teacher_model_path)

        # Training state
        self.global_step = 0
        self.epoch = 0
        self.best_val_loss = float("inf")

    def _load_teacher_model(self, path: str) -> None:
        """Load teacher model for distillation."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        # Assuming teacher model has same architecture but larger
        # In practice, you'd load a larger model here
        self.teacher_model = create_model(checkpoint.get("config", self.model.config))
        self.teacher_model.load_state_dict(checkpoint["model_state_dict"])
        self.teacher_model.to(self.device)
        self.teacher_model.eval()
        for param in self.teacher_model.parameters():
            param.requires_grad = False

    def compute_loss(
        self,
        logits: torch.Tensor,
        targets: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Compute cross-entropy loss with optional distillation."""
        # Flatten for cross-entropy
        logits_flat = logits.view(-1, logits.size(-1))
        targets_flat = targets.view(-1)
        mask_flat = attention_mask.view(-1)

        # Standard cross-entropy
        loss = F.cross_entropy(
            logits_flat,
            targets_flat,
            ignore_index=self.tokenizer.pad_token_id,
            reduction="none",
        )

        # Apply mask
        loss = (loss * mask_flat).sum() / mask_flat.sum().clamp(min=1)

        # Distillation loss
        if self.distillation and self.teacher_model is not None:
            with torch.no_grad():
                teacher_logits = self.teacher_model(input_ids=None)["logits"]  # placeholder
            # KL divergence between student and teacher
            distill_loss = F.kl_div(
                F.log_softmax(logits_flat / 2.0, dim=-1),
                F.softmax(teacher_logits.view(-1, teacher_logits.size(-1)) / 2.0, dim=-1),
                reduction="batchmean",
            ) * (2.0 ** 2)
            loss = 0.5 * loss + 0.5 * distill_loss

        return loss

    def train_step(self, batch: dict[str, torch.Tensor]) -> dict[str, float]:
        """Single training step."""
        self.model.train()

        input_ids = batch["input_ids"].to(self.device)
        target_ids = batch["target_ids"].to(self.device)
        attention_mask = batch["attention_mask"].to(self.device)
        metadata_embeddings = self._encode_batch_metadata(batch)

        # Forward pass with mixed precision
        with autocast(enabled=self.mixed_precision):
            outputs = self.model(
                input_ids, attention_mask=attention_mask, metadata_embeddings=metadata_embeddings
            )
            loss = self.compute_loss(outputs["logits"], target_ids, attention_mask)

        # Backward pass
        self.optimizer.zero_grad()
        self.scaler.scale(loss).backward()

        # Gradient clipping
        if self.gradient_clip > 0:
            self.scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.gradient_clip)

        self.scaler.step(self.optimizer)
        self.scaler.update()

        self.global_step += 1

        return {
            "loss": loss.item(),
            "lr": self.optimizer.param_groups[0]["lr"],
        }

    def _encode_batch_metadata(self, batch: dict[str, torch.Tensor]) -> torch.Tensor | None:
        """Run the model's MetadataEncoder over a batch's metadata_ids, if present."""
        metadata_ids = batch.get("metadata_ids")
        if metadata_ids is None:
            return None
        return self.model.encode_metadata(metadata_ids.to(self.device))

    @torch.no_grad()
    def validate(self, val_loader: torch.utils.data.DataLoader) -> dict[str, float]:
        """Validation loop."""
        self.model.eval()
        total_loss = 0.0
        total_tokens = 0
        correct = 0

        for batch in val_loader:
            input_ids = batch["input_ids"].to(self.device)
            target_ids = batch["target_ids"].to(self.device)
            attention_mask = batch["attention_mask"].to(self.device)
            metadata_embeddings = self._encode_batch_metadata(batch)

            with autocast(enabled=self.mixed_precision):
                outputs = self.model(
                    input_ids, attention_mask=attention_mask, metadata_embeddings=metadata_embeddings
                )
                loss = self.compute_loss(outputs["logits"], target_ids, attention_mask)

            total_loss += loss.item() * attention_mask.sum().item()
            total_tokens += attention_mask.sum().item()

            # Accuracy
            preds = outputs["logits"].argmax(dim=-1)
            correct += ((preds == target_ids) & attention_mask.bool()).sum().item()

        avg_loss = total_loss / total_tokens if total_tokens > 0 else float("inf")
        accuracy = correct / total_tokens if total_tokens > 0 else 0.0
        perplexity = math.exp(min(avg_loss, 20))  # Cap for numerical stability

        return {
            "val_loss": avg_loss,
            "val_accuracy": accuracy,
            "val_perplexity": perplexity,
        }

    def save_checkpoint(self, path: str | Path, is_best: bool = False) -> None:
        """Save model checkpoint."""
        checkpoint = {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scaler_state_dict": self.scaler.state_dict(),
            "config": self.model.config,
            "training_config": self.config,
            "global_step": self.global_step,
            "epoch": self.epoch,
            "best_val_loss": self.best_val_loss,
            "tokenizer_config": {
                "vocab_size": self.tokenizer.vocab_size,
                "max_seq_len": self.tokenizer.max_seq_len,
                "pad_token_id": self.tokenizer.pad_token_id,
                "bos_token_id": self.tokenizer.bos_token_id,
                "eos_token_id": self.tokenizer.eos_token_id,
                "unk_token_id": self.tokenizer.unk_token_id,
            },
            # Persist the metadata vocabulary so inference can tokenize breach
            # context (organization/year/known_leaks) into the same IDs the
            # model's MetadataEncoder was trained on. Without this, a reloaded
            # generator has no way to reproduce the training-time vocabulary
            # and context conditioning silently degrades to near-random IDs.
            "metadata_vocab": (
                {
                    "word_to_id": self.metadata_tokenizer.word_to_id,
                    "max_metadata_tokens": self.metadata_tokenizer.max_metadata_tokens,
                }
                if self.metadata_tokenizer is not None
                else None
            ),
        }
        torch.save(checkpoint, path)
        if is_best:
            best_path = Path(path).parent / "best_model.pt"
            torch.save(checkpoint, best_path)

    def load_checkpoint(self, path: str | Path) -> None:
        """Load model checkpoint."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.scaler.load_state_dict(checkpoint["scaler_state_dict"])
        self.global_step = checkpoint["global_step"]
        self.epoch = checkpoint["epoch"]
        self.best_val_loss = checkpoint["best_val_loss"]


def create_scheduler(
    optimizer: torch.optim.Optimizer,
    config: TrainingConfig,
    num_training_steps: int,
) -> torch.optim.lr_scheduler.SequentialLR:
    """Create learning rate scheduler with warmup."""
    warmup_steps = config.warmup_steps
    warmup_scheduler = LinearLR(
        optimizer,
        start_factor=0.01,
        end_factor=1.0,
        total_iters=warmup_steps,
    )
    cosine_scheduler = CosineAnnealingLR(
        optimizer,
        T_max=num_training_steps - warmup_steps,
        eta_min=config.learning_rate * 0.01,
    )
    return SequentialLR(
        optimizer,
        schedulers=[warmup_scheduler, cosine_scheduler],
        milestones=[warmup_steps],
    )


def train(
    train_loader: torch.utils.data.DataLoader,
    val_loader: torch.utils.data.DataLoader | None,
    model: NCGTransformer,
    config: TrainingConfig,
    tokenizer: PasswordTokenizer,
    device: torch.device,
    output_dir: str | Path,
    log_interval: int = 100,
    eval_interval: int = 1000,
    save_interval: int = 5000,
    metadata_tokenizer: MetadataTokenizer | None = None,
) -> NCGTransformer:
    """Main training loop."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trainer = NCGTrainer(model, config, device, tokenizer, metadata_tokenizer=metadata_tokenizer)
    scheduler = create_scheduler(trainer.optimizer, config, len(train_loader) * config.max_epochs)

    logger.info("Starting training on %s", device)
    logger.info("Model parameters: %s", f"{sum(p.numel() for p in model.parameters()):,}")

    for epoch in range(config.max_epochs):
        trainer.epoch = epoch
        epoch_start = time.time()

        for _step, batch in enumerate(train_loader):
            step_metrics = trainer.train_step(batch)

            if trainer.global_step % log_interval == 0:
                logger.info(
                    "Step %d | Loss: %.4f | LR: %.2e",
                    trainer.global_step,
                    step_metrics["loss"],
                    step_metrics["lr"],
                )

            # Evaluation
            if val_loader and trainer.global_step % eval_interval == 0:
                val_metrics = trainer.validate(val_loader)
                logger.info(
                    "Validation | Loss: %.4f | Acc: %.4f | PPL: %.2f",
                    val_metrics["val_loss"],
                    val_metrics["val_accuracy"],
                    val_metrics["val_perplexity"],
                )

                # Save best model
                if val_metrics["val_loss"] < trainer.best_val_loss:
                    trainer.best_val_loss = val_metrics["val_loss"]
                    trainer.save_checkpoint(output_dir / f"checkpoint_step_{trainer.global_step}.pt", is_best=True)

            # Regular checkpoint
            if trainer.global_step % save_interval == 0:
                trainer.save_checkpoint(output_dir / f"checkpoint_step_{trainer.global_step}.pt")

            scheduler.step()

        epoch_time = time.time() - epoch_start
        logger.info("Epoch %d/%d completed in %.1fs", epoch + 1, config.max_epochs, epoch_time)

        # End of epoch checkpoint
        trainer.save_checkpoint(output_dir / f"checkpoint_epoch_{epoch + 1}.pt")

    # Final save
    trainer.save_checkpoint(output_dir / "final_model.pt", is_best=True)
    logger.info("Training completed!")

    return model
