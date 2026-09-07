"""Inference engine for DCPM generation in NCG Framework."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from ncg.config import InferenceConfig, ModelConfig

from .data import BreachContext
from .model import NCGTransformer, create_model
from .tokenizer import MetadataTokenizer, PasswordTokenizer

logger = logging.getLogger(__name__)


class DCPMGenerator:
    """Generator for Dynamic Candidate Probability Matrix (DCPM)."""

    def __init__(
        self,
        model: NCGTransformer,
        tokenizer: PasswordTokenizer,
        metadata_tokenizer: MetadataTokenizer | None = None,
        inference_config: InferenceConfig | None = None,
        device: torch.device = torch.device("cpu"),
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.metadata_tokenizer = metadata_tokenizer
        self.inference_config = inference_config or InferenceConfig()
        self.device = device

        self.model.to(device)
        self.model.eval()

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str | Path,
        device: torch.device = torch.device("cpu"),
        inference_config: InferenceConfig | None = None,
    ) -> DCPMGenerator:
        """Load generator from checkpoint."""
        # weights_only=False required: checkpoint contains ModelConfig/TrainingConfig objects
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

        # Recreate model
        model_config = checkpoint.get("config", ModelConfig())
        model = create_model(model_config)
        model.load_state_dict(checkpoint["model_state_dict"])

        # Recreate tokenizer
        tokenizer_config = checkpoint.get("tokenizer_config", {})
        tokenizer = PasswordTokenizer(**tokenizer_config)

        # Restore the metadata vocabulary the model's MetadataEncoder was
        # trained on, if this checkpoint was trained with breach-context
        # conditioning. Without this, encode_context() would tokenize
        # organization/year/etc into a fresh, empty vocab and every word
        # would map to [UNK] -- silently discarding the learned conditioning.
        metadata_tokenizer = None
        metadata_vocab = checkpoint.get("metadata_vocab")
        if metadata_vocab:
            metadata_tokenizer = MetadataTokenizer(
                max_metadata_tokens=metadata_vocab.get("max_metadata_tokens", 32)
            )
            metadata_tokenizer.word_to_id = dict(metadata_vocab["word_to_id"])
            metadata_tokenizer.id_to_word = {v: k for k, v in metadata_tokenizer.word_to_id.items()}
            metadata_tokenizer.next_id = max(metadata_tokenizer.word_to_id.values(), default=3) + 1

        return cls(model, tokenizer, metadata_tokenizer, inference_config, device)

    def encode_context(self, context: BreachContext) -> torch.Tensor:
        """Encode breach context into a learned metadata conditioning vector.

        Uses the model's own MetadataEncoder (trained end-to-end via the
        language-modeling loss), so organization/year/known_leaks/etc. actually
        change the resulting embedding -- and therefore generation -- instead
        of always producing a zero vector.
        """
        if self.metadata_tokenizer is None:
            # This model checkpoint was never trained with breach-context
            # metadata (e.g. a plain-text password file with no --metadata),
            # so there is no learned vocabulary to encode against. Returning
            # zeros here is honest: context truly has no effect on this model.
            return torch.zeros(1, self.model.d_model, device=self.device)

        ids = self.metadata_tokenizer.encode_metadata(context.to_dict())
        ids_tensor = torch.tensor([ids], dtype=torch.long, device=self.device)
        with torch.no_grad():
            return self.model.encode_metadata(ids_tensor)

    def generate_candidates(
        self,
        context: BreachContext | dict[str, Any],
        num_candidates: int = 1000,
        max_length: int = 64,
        temperature: float = 1.0,
        top_k: int = 50,
        top_p: float = 0.9,
        batch_size: int = 32,
    ) -> list[str]:
        """Generate password candidates from context."""
        if isinstance(context, dict):
            context = BreachContext.from_dict(context)

        metadata_emb = self.encode_context(context)
        candidates = []

        with torch.no_grad():
            for i in range(0, num_candidates, batch_size):
                curr_batch = min(batch_size, num_candidates - i)

                # Start with BOS token
                input_ids = torch.full(
                    (curr_batch, 1),
                    self.tokenizer.bos_token_id,
                    dtype=torch.long,
                    device=self.device,
                )

                # Generate sequences
                for _ in range(max_length - 1):
                    outputs = self.model(input_ids, metadata_embeddings=metadata_emb)
                    logits = outputs["logits"][:, -1, :] / temperature

                    # Top-k filtering
                    if top_k > 0:
                        top_k_logits, top_k_indices = torch.topk(logits, top_k, dim=-1)
                        logits_filtered = torch.full_like(logits, float("-inf"))
                        logits_filtered.scatter_(-1, top_k_indices, top_k_logits)
                        logits = logits_filtered

                    # Top-p filtering
                    if top_p < 1.0:
                        sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
                        cumsum_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
                        sorted_indices_to_remove = cumsum_probs > top_p
                        sorted_indices_to_remove[:, 1:] = sorted_indices_to_remove[:, :-1].clone()
                        sorted_indices_to_remove[:, 0] = 0
                        indices_to_remove = sorted_indices_to_remove.scatter(
                            -1, sorted_indices, sorted_indices_to_remove
                        )
                        logits[indices_to_remove] = float("-inf")

                    # Sample
                    probs = F.softmax(logits, dim=-1)
                    next_token = torch.multinomial(probs, num_samples=1)

                    input_ids = torch.cat([input_ids, next_token], dim=1)

                    # Check for EOS
                    if (next_token == self.tokenizer.eos_token_id).all():
                        break

                # Decode batch
                for j in range(curr_batch):
                    candidate = self.tokenizer.decode(
                        input_ids[j].tolist(), skip_special_tokens=True
                    )
                    if candidate:
                        candidates.append(candidate)

        return candidates

    def generate_dcmp(
        self,
        context: BreachContext | dict[str, Any],
        prefix: str = "",
        max_length: int = 64,
    ) -> torch.Tensor:
        """Generate full Dynamic Candidate Probability Matrix for a context.

        Returns tensor of shape [seq_len, vocab_size] with conditional probabilities.
        """
        if isinstance(context, dict):
            context = BreachContext.from_dict(context)

        metadata_emb = self.encode_context(context)

        # Encode prefix
        if prefix:
            prefix_ids = self.tokenizer.encode(prefix, add_special_tokens=True)
            input_ids = torch.tensor([prefix_ids], dtype=torch.long, device=self.device)
        else:
            input_ids = torch.tensor(
                [[self.tokenizer.bos_token_id]], dtype=torch.long, device=self.device
            )

        self.model.eval()
        with torch.no_grad():
            outputs = self.model(input_ids, metadata_embeddings=metadata_emb)
            logits = outputs["logits"]  # [1, seq_len, vocab_size]

            # Get probabilities for each position
            probs = F.softmax(logits[0], dim=-1)  # [seq_len, vocab_size]

        return probs

    def score_candidates(
        self,
        candidates: list[str],
        context: BreachContext | dict[str, Any],
    ) -> list[tuple[str, float]]:
        """Score a list of candidates given context."""
        if isinstance(context, dict):
            context = BreachContext.from_dict(context)

        metadata_emb = self.encode_context(context)
        scored = []

        self.model.eval()
        with torch.no_grad():
            for candidate in candidates:
                encoded = self.tokenizer.encode(candidate, add_special_tokens=True)
                input_ids = torch.tensor([encoded[:-1]], dtype=torch.long, device=self.device)
                target_ids = torch.tensor([encoded[1:]], dtype=torch.long, device=self.device)

                outputs = self.model(input_ids, metadata_embeddings=metadata_emb)
                logits = outputs["logits"][0]  # [seq_len, vocab_size]

                # Compute log probability
                log_probs = F.log_softmax(logits, dim=-1)
                token_log_probs = log_probs.gather(-1, target_ids[0].unsqueeze(-1)).squeeze(-1)
                score = token_log_probs.mean().item()  # Average log probability

                scored.append((candidate, score))

        # Sort by score (descending)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


def load_generator(
    model_path: str | Path,
    device: str | torch.device = "auto",
    inference_config: InferenceConfig | None = None,
) -> DCPMGenerator:
    """Convenience function to load a DCPM generator."""
    if device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    elif isinstance(device, str):
        device = torch.device(device)

    return DCPMGenerator.from_checkpoint(model_path, device, inference_config)


def demo_generation() -> None:
    """Demo function for testing generation."""
    logger = logging.getLogger(__name__)

    # Create dummy model for testing
    config = ModelConfig(vocab_size=100, max_seq_len=32, d_model=128, n_heads=4, n_layers=2)
    model = create_model(config)
    tokenizer = PasswordTokenizer(max_seq_len=32)

    generator = DCPMGenerator(model, tokenizer)

    context = BreachContext(
        organization="TechCorp",
        year=2026,
        known_leaks=["admin", "password", "techcorp"],
    )

    candidates = generator.generate_candidates(context, num_candidates=10, max_length=16)
    logger.info("Generated candidates:")
    for c in candidates:
        logger.info("  %s", c)


if __name__ == "__main__":
    demo_generation()
