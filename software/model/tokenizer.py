"""Custom tokenizer for password patterns in NCG Framework."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import torch
from torch.nn.utils.rnn import pad_sequence

# Printable ASCII characters (32-126) + special tokens
PRINTABLE_ASCII = [chr(i) for i in range(32, 127)]
VOCAB_SIZE = len(PRINTABLE_ASCII) + 4  # +4 for special tokens

# Special token IDs
PAD_TOKEN_ID = 0
BOS_TOKEN_ID = 1
EOS_TOKEN_ID = 2
UNK_TOKEN_ID = 3

# Character to ID mapping (offset by 4 for special tokens)
CHAR_TO_ID = {ch: i + 4 for i, ch in enumerate(PRINTABLE_ASCII)}
ID_TO_CHAR = {i + 4: ch for i, ch in enumerate(PRINTABLE_ASCII)}
ID_TO_CHAR[PAD_TOKEN_ID] = "[PAD]"
ID_TO_CHAR[BOS_TOKEN_ID] = "[BOS]"
ID_TO_CHAR[EOS_TOKEN_ID] = "[EOS]"
ID_TO_CHAR[UNK_TOKEN_ID] = "[UNK]"


class PasswordTokenizer:
    """Tokenizer for password candidate generation."""

    def __init__(
        self,
        vocab_size: int = VOCAB_SIZE,
        max_seq_len: int = 64,
        pad_token_id: int = PAD_TOKEN_ID,
        bos_token_id: int = BOS_TOKEN_ID,
        eos_token_id: int = EOS_TOKEN_ID,
        unk_token_id: int = UNK_TOKEN_ID,
    ):
        self.vocab_size = vocab_size
        self.max_seq_len = max_seq_len
        self.pad_token_id = pad_token_id
        self.bos_token_id = bos_token_id
        self.eos_token_id = eos_token_id
        self.unk_token_id = unk_token_id

    def encode(self, text: str, add_special_tokens: bool = True) -> list[int]:
        """Encode text to token IDs."""
        ids = []
        if add_special_tokens:
            ids.append(self.bos_token_id)

        for ch in text:
            if ch in CHAR_TO_ID:
                ids.append(CHAR_TO_ID[ch])
            else:
                ids.append(self.unk_token_id)

        if add_special_tokens:
            ids.append(self.eos_token_id)

        # Truncate if too long
        if len(ids) > self.max_seq_len:
            if add_special_tokens:
                ids = ids[: self.max_seq_len - 1] + [self.eos_token_id]
            else:
                ids = ids[: self.max_seq_len]

        return ids

    def decode(self, ids: list[int], skip_special_tokens: bool = True) -> str:
        """Decode token IDs to text."""
        chars = []
        for id_ in ids:
            if skip_special_tokens and id_ in (
                self.pad_token_id,
                self.bos_token_id,
                self.eos_token_id,
                self.unk_token_id,
            ):
                continue
            chars.append(ID_TO_CHAR.get(id_, "[UNK]"))
        return "".join(chars)

    def encode_batch(
        self, texts: list[str], add_special_tokens: bool = True, padding: bool = True
    ) -> torch.Tensor | list[torch.Tensor]:
        """Encode a batch of texts."""
        encoded = [self.encode(t, add_special_tokens) for t in texts]
        if padding:
            return pad_sequence(
                [torch.tensor(e, dtype=torch.long) for e in encoded],
                batch_first=True,
                padding_value=self.pad_token_id,
            )
        return [torch.tensor(e, dtype=torch.long) for e in encoded]

    def decode_batch(self, ids_batch: torch.Tensor, skip_special_tokens: bool = True) -> list[str]:
        """Decode a batch of token IDs."""
        return [self.decode(ids.tolist(), skip_special_tokens) for ids in ids_batch]

    def save_pretrained(self, path: str | Path) -> None:
        """Save tokenizer configuration."""
        config = {
            "vocab_size": self.vocab_size,
            "max_seq_len": self.max_seq_len,
            "pad_token_id": self.pad_token_id,
            "bos_token_id": self.bos_token_id,
            "eos_token_id": self.eos_token_id,
            "unk_token_id": self.unk_token_id,
        }
        with open(Path(path) / "tokenizer_config.json", "w") as f:
            json.dump(config, f, indent=2)

    @classmethod
    def from_pretrained(cls, path: str | Path) -> PasswordTokenizer:
        """Load tokenizer from configuration."""
        with open(Path(path) / "tokenizer_config.json") as f:
            config = json.load(f)
        return cls(**config)


class MetadataTokenizer:
    """Tokenizer for target metadata (organization, year, leaks, etc.)."""

    def __init__(self, max_metadata_tokens: int = 128):
        self.max_metadata_tokens = max_metadata_tokens
        # Simple word-level tokenization for metadata
        self.word_to_id: dict[str, int] = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3}
        self.id_to_word: dict[int, str] = {v: k for k, v in self.word_to_id.items()}
        self.next_id = 4

    def build_vocab(self, metadata_list: list[dict[str, Any]]) -> None:
        """Build vocabulary from metadata samples."""
        for metadata in metadata_list:
            for _key, value in metadata.items():
                if isinstance(value, str):
                    words = re.findall(r"\w+", value.lower())
                    for word in words:
                        if word not in self.word_to_id:
                            self.word_to_id[word] = self.next_id
                            self.id_to_word[self.next_id] = word
                            self.next_id += 1
                elif isinstance(value, (int, float)):
                    word = str(value)
                    if word not in self.word_to_id:
                        self.word_to_id[word] = self.next_id
                        self.id_to_word[self.next_id] = word
                        self.next_id += 1

    def encode_metadata(self, metadata: dict[str, Any]) -> list[int]:
        """Encode metadata dict to token IDs."""
        tokens = [self.word_to_id["[CLS]"]]
        for key, value in metadata.items():
            key_tokens = re.findall(r"\w+", key.lower())
            for kt in key_tokens:
                tokens.append(self.word_to_id.get(kt, self.word_to_id["[UNK]"]))

            if isinstance(value, str):
                val_tokens = re.findall(r"\w+", value.lower())
                for vt in val_tokens:
                    tokens.append(self.word_to_id.get(vt, self.word_to_id["[UNK]"]))
            elif isinstance(value, (int, float)):
                tokens.append(self.word_to_id.get(str(value), self.word_to_id["[UNK]"]))

            tokens.append(self.word_to_id["[SEP]"])

        # Truncate or pad
        if len(tokens) > self.max_metadata_tokens:
            tokens = tokens[: self.max_metadata_tokens]
        else:
            tokens += [self.word_to_id["[PAD]"]] * (self.max_metadata_tokens - len(tokens))

        return tokens

    def get_vocab_size(self) -> int:
        return self.next_id
