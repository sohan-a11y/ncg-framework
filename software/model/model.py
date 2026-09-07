"""Quantized Transformer model for NCG Framework."""

from __future__ import annotations

import math
from typing import cast

import torch
import torch.nn as nn
import torch.nn.functional as F
from ncg.config import ModelConfig


def fake_quantize_int4(w: torch.Tensor) -> torch.Tensor:
    """Differentiable per-channel INT4 fake-quantization (straight-through estimator).

    Simulates the round-trip through INT4 (16 levels) in the forward pass so the
    model learns weights that survive quantization, while gradients flow to the
    real-valued weight unchanged (STE) so training remains stable.
    """
    w_min = w.min(dim=1, keepdim=True)[0]
    w_max = w.max(dim=1, keepdim=True)[0]
    scale = ((w_max - w_min) / 15).clamp(min=1e-8)  # 4-bit = 16 levels
    zero_point = (-w_min / scale).round().clamp(0, 15)
    w_q = ((w / scale) + zero_point).round().clamp(0, 15)
    w_dq = (w_q - zero_point) * scale
    # Straight-through estimator: forward uses the quantized value, backward
    # treats it as identity so gradients still update the fp32 weight.
    return w + (w_dq - w).detach()


class QuantizedLinear(nn.Module):
    """Linear layer with INT4 quantization support."""

    weight_scale: torch.Tensor
    weight_zero_point: torch.Tensor
    weight_q: torch.Tensor | None

    def __init__(
        self,
        in_features: int,
        out_features: int,
        bias: bool = True,
        quantization: str = "int4",
    ):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.quantization = quantization
        # When True and the module is in training mode, forward() fake-quantizes
        # weights (QAT). Set via NCGTransformer.set_qat_enabled(); defaults off
        # so plain FP32 training is unaffected unless explicitly requested.
        self.qat_enabled = False

        self.weight = nn.Parameter(torch.empty(out_features, in_features))
        if bias:
            self.bias = nn.Parameter(torch.empty(out_features))
        else:
            self.register_parameter("bias", None)

        self.register_buffer("weight_scale", torch.ones(out_features))
        self.register_buffer("weight_zero_point", torch.zeros(out_features, dtype=torch.int32))
        self.weight_q = None

        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = nn.init._calculate_fan_in_and_fan_out(self.weight)
            bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
            nn.init.uniform_(self.bias, -bound, bound)

    def quantize_weights(self) -> None:
        """Quantize weights to INT4."""
        if self.quantization == "int4":
            # Per-channel quantization
            w = self.weight.data
            w_min = w.min(dim=1, keepdim=True)[0]
            w_max = w.max(dim=1, keepdim=True)[0]
            scale = (w_max - w_min) / 15  # 4-bit = 16 levels
            scale = scale.clamp(min=1e-8)
            zero_point = (-w_min / scale).round().clamp(0, 15).to(torch.int32)

            self.weight_scale.copy_(scale.squeeze())
            self.weight_zero_point.copy_(zero_point.squeeze())

            # Store quantized weights
            w_q = ((w / scale) + zero_point).round().clamp(0, 15).to(torch.uint8)
            self.weight_q = w_q

    def dequantize_weights(self) -> torch.Tensor:
        """Dequantize weights for computation."""
        if self.weight_q is not None:
            scale = self.weight_scale.unsqueeze(1)
            zero_point = self.weight_zero_point.unsqueeze(1)
            return (self.weight_q.to(torch.float32) - zero_point) * scale
        return self.weight

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.training and self.qat_enabled and self.quantization == "int4":
            weight = fake_quantize_int4(self.weight)
        else:
            weight = self.dequantize_weights()
        return F.linear(x, weight, self.bias)


class QuantizedMultiheadAttention(nn.Module):
    """Multi-head attention with quantized projections."""

    def __init__(
        self,
        d_model: int,
        n_heads: int,
        dropout: float = 0.1,
        quantization: str = "int4",
    ):
        super().__init__()
        assert d_model % n_heads == 0
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads

        self.q_proj = QuantizedLinear(d_model, d_model, quantization=quantization)
        self.k_proj = QuantizedLinear(d_model, d_model, quantization=quantization)
        self.v_proj = QuantizedLinear(d_model, d_model, quantization=quantization)
        self.out_proj = QuantizedLinear(d_model, d_model, quantization=quantization)

        self.dropout = nn.Dropout(dropout)
        self.scale = 1 / math.sqrt(self.head_dim)

    def forward(
        self,
        query: torch.Tensor,
        key: torch.Tensor,
        value: torch.Tensor,
        attn_mask: torch.Tensor | None = None,
        key_padding_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        batch_size, seq_len, _ = query.shape

        # Project
        q = self.q_proj(query).view(batch_size, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(key).view(batch_size, -1, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(value).view(batch_size, -1, self.n_heads, self.head_dim).transpose(1, 2)

        # Attention
        attn_weights = torch.matmul(q, k.transpose(-2, -1)) * self.scale

        if attn_mask is not None:
            attn_weights += attn_mask

        if key_padding_mask is not None:
            # key_padding_mask: [batch, seq] -> [batch, 1, 1, seq]
            kpm = key_padding_mask.unsqueeze(1).unsqueeze(2)
            attn_weights = attn_weights.masked_fill(kpm, float("-inf"))

        attn_weights = F.softmax(attn_weights, dim=-1)
        attn_weights = self.dropout(attn_weights)

        # Output
        out = torch.matmul(attn_weights, v)
        out = out.transpose(1, 2).contiguous().view(batch_size, seq_len, self.d_model)
        out = self.out_proj(out)

        return out, attn_weights


class QuantizedFeedForward(nn.Module):
    """Feed-forward network with quantized linear layers."""

    def __init__(
        self,
        d_model: int,
        d_ff: int,
        dropout: float = 0.1,
        quantization: str = "int4",
        activation: str = "gelu",
    ):
        super().__init__()
        self.linear1 = QuantizedLinear(d_model, d_ff, quantization=quantization)
        self.linear2 = QuantizedLinear(d_ff, d_model, quantization=quantization)
        self.dropout = nn.Dropout(dropout)
        self.activation = F.gelu if activation == "gelu" else F.relu

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.linear1(x)
        x = self.activation(x)
        x = self.dropout(x)
        x = self.linear2(x)
        return x


class TransformerBlock(nn.Module):
    """Single Transformer encoder block with quantization."""

    def __init__(
        self,
        d_model: int,
        n_heads: int,
        d_ff: int,
        dropout: float = 0.1,
        quantization: str = "int4",
    ):
        super().__init__()
        self.attention = QuantizedMultiheadAttention(d_model, n_heads, dropout, quantization)
        self.feed_forward = QuantizedFeedForward(d_model, d_ff, dropout, quantization)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        attn_mask: torch.Tensor | None = None,
        key_padding_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        # Self-attention with residual
        attn_out, _ = self.attention(x, x, x, attn_mask, key_padding_mask)
        x = self.norm1(x + self.dropout(attn_out))

        # Feed-forward with residual
        ff_out = self.feed_forward(x)
        x = self.norm2(x + self.dropout(ff_out))

        return x


class MetadataEncoder(nn.Module):
    """Encodes breach-context metadata (organization, year, leaks, ...) into a
    single embedding conditioning vector.

    Takes the token-ID sequence produced by MetadataTokenizer.encode_metadata()
    and mean-pools the (learned) embeddings of its non-PAD tokens. Being a real
    nn.Module owned by NCGTransformer, its weights are trained end-to-end via
    the language-modeling loss and persist in the model checkpoint, so context
    conditioning is actually learned rather than computed from an untrained,
    thrown-away encoding.
    """

    def __init__(self, vocab_size: int, d_model: int, pad_token_id: int = 0):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=pad_token_id)
        self.pad_token_id = pad_token_id

    def forward(self, metadata_ids: torch.Tensor) -> torch.Tensor:
        """metadata_ids: [batch, seq] -> conditioning vector [batch, d_model]."""
        mask = (metadata_ids != self.pad_token_id).unsqueeze(-1).to(self.embedding.weight.dtype)
        emb = self.embedding(metadata_ids) * mask
        summed = emb.sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1.0)
        return cast(torch.Tensor, summed / counts)


class NCGTransformer(nn.Module):
    """NCG Transformer model for Dynamic Candidate Probability Matrix (DCPM) generation."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.vocab_size = config.vocab_size
        self.max_seq_len = config.max_seq_len
        self.d_model = config.d_model
        self.pad_token_id = config.pad_token_id

        # Embeddings
        self.token_embedding = nn.Embedding(config.vocab_size, config.d_model, padding_idx=config.pad_token_id)
        self.position_embedding = nn.Embedding(config.max_seq_len, config.d_model)

        # Transformer blocks
        self.blocks = nn.ModuleList([
            TransformerBlock(
                config.d_model,
                config.n_heads,
                config.d_ff,
                config.dropout,
                config.quantization,
            )
            for _ in range(config.n_layers)
        ])

        # Metadata (breach-context) encoder: learned conditioning vector from
        # organization/year/known_leaks/etc, added to the sequence in forward().
        self.metadata_encoder = MetadataEncoder(
            config.metadata_vocab_size, config.d_model, pad_token_id=0
        )

        # Output head for DCPM generation
        self.ln_f = nn.LayerNorm(config.d_model)
        self.dcmp_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        # Tie weights
        self.dcmp_head.weight = self.token_embedding.weight

        self.dropout = nn.Dropout(config.dropout)
        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module) -> None:
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.LayerNorm):
            nn.init.ones_(module.weight)
            nn.init.zeros_(module.bias)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        metadata_embeddings: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        batch_size, seq_len = input_ids.shape

        # Create position IDs
        position_ids = torch.arange(seq_len, device=input_ids.device).unsqueeze(0).expand(batch_size, -1)

        # Embeddings
        token_emb = self.token_embedding(input_ids)
        pos_emb = self.position_embedding(position_ids)
        x = self.dropout(token_emb + pos_emb)

        # Add metadata embeddings if provided (simple addition at first position)
        if metadata_embeddings is not None:
            x[:, 0, :] = x[:, 0, :] + metadata_embeddings

        # Causal attention mask [seq, seq] -> broadcasts as [1, 1, seq, seq]
        causal_mask = torch.triu(
            torch.ones(seq_len, seq_len, device=input_ids.device) * float("-inf"),
            diagonal=1,
        )

        if attention_mask is not None:
            # Padding mask [batch, seq] -> [batch, 1, 1, seq] for broadcasting
            pad_mask = (1.0 - attention_mask.to(torch.float32)) * -10000.0
            pad_mask = pad_mask.unsqueeze(1).unsqueeze(2)
            # Combine: [batch, 1, 1, seq] + [seq, seq] -> [batch, 1, seq, seq]
            causal_mask = causal_mask.unsqueeze(0).unsqueeze(0) + pad_mask

        # Transformer blocks
        for block in self.blocks:
            x = block(x, attn_mask=causal_mask)

        x = self.ln_f(x)

        # DCPM logits (next token prediction)
        logits = self.dcmp_head(x)

        return {
            "logits": logits,
            "hidden_states": x,
        }

    def encode_metadata(self, metadata_ids: torch.Tensor) -> torch.Tensor:
        """Encode a batch of tokenized breach-context metadata into conditioning
        vectors, using the model's own learned MetadataEncoder."""
        return cast(torch.Tensor, self.metadata_encoder(metadata_ids))

    def generate_dcmp(
        self,
        context_ids: torch.Tensor,
        metadata_embeddings: torch.Tensor | None = None,
        temperature: float = 1.0,
        top_k: int = 50,
        top_p: float = 0.9,
        max_new_tokens: int = 64,
    ) -> torch.Tensor:
        """Generate Dynamic Candidate Probability Matrix (DCPM) for given context."""
        self.eval()
        with torch.no_grad():
            generated = context_ids.clone()

            for _ in range(max_new_tokens):
                # Forward pass
                outputs = self.forward(generated, metadata_embeddings=metadata_embeddings)
                logits = outputs["logits"][:, -1, :] / temperature

                # Top-k filtering
                if top_k > 0:
                    top_k_logits, top_k_indices = torch.topk(logits, top_k, dim=-1)
                    logits = torch.full_like(logits, float("-inf"))
                    logits.scatter_(-1, top_k_indices, top_k_logits)

                # Top-p (nucleus) filtering
                if top_p < 1.0:
                    sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
                    cumsum_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
                    sorted_indices_to_remove = cumsum_probs > top_p
                    sorted_indices_to_remove[:, 1:] = sorted_indices_to_remove[:, :-1].clone()
                    sorted_indices_to_remove[:, 0] = 0
                    indices_to_remove = sorted_indices_to_remove.scatter(-1, sorted_indices, sorted_indices_to_remove)
                    logits[indices_to_remove] = float("-inf")

                # Sample next token
                probs = F.softmax(logits, dim=-1)
                next_token = torch.multinomial(probs, num_samples=1)

                # Append to generated sequence
                generated = torch.cat([generated, next_token], dim=1)

                # Stop if EOS token generated
                if (next_token == self.config.eos_token_id).all():
                    break

        # Return DCPM: conditional probabilities for each position
        return generated

    def set_qat_enabled(self, enabled: bool) -> None:
        """Enable/disable quantization-aware training on all quantized layers.

        When enabled, QuantizedLinear.forward() fake-quantizes weights to INT4
        during training (self.training is True), so gradient descent adapts
        weights to survive quantization instead of INT4 only being applied
        after training at export time.
        """
        for module in self.modules():
            if isinstance(module, QuantizedLinear):
                module.qat_enabled = enabled

    def quantize_model(self) -> None:
        """Quantize all quantizable layers."""
        for block_module in self.blocks:
            block = cast(TransformerBlock, block_module)
            block.attention.q_proj.quantize_weights()
            block.attention.k_proj.quantize_weights()
            block.attention.v_proj.quantize_weights()
            block.attention.out_proj.quantize_weights()
            block.feed_forward.linear1.quantize_weights()
            block.feed_forward.linear2.quantize_weights()


def create_model(config: ModelConfig) -> NCGTransformer:
    """Factory function to create NCG Transformer model."""
    return NCGTransformer(config)
