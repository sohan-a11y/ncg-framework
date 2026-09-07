"""Data pipeline and breach context parser for NCG Framework."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader, Dataset

from .tokenizer import MetadataTokenizer, PasswordTokenizer


class BreachContext:
    """Structured representation of target metadata/breach context."""

    def __init__(
        self,
        organization: str = "",
        year: int | None = None,
        known_leaks: list[str] | None = None,
        industry: str = "",
        location: str = "",
        additional: dict[str, Any] | None = None,
    ):
        self.organization = organization
        self.year = year
        self.known_leaks = known_leaks or []
        self.industry = industry
        self.location = location
        self.additional = additional or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization": self.organization,
            "year": self.year,
            "known_leaks": self.known_leaks,
            "industry": self.industry,
            "location": self.location,
            **self.additional,
        }

    @classmethod
    def from_json(cls, path: str | Path) -> BreachContext:
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BreachContext:
        return cls(**data)


class PasswordDataset(Dataset):
    """Dataset for password training data."""

    def __init__(
        self,
        passwords: list[str],
        tokenizer: PasswordTokenizer,
        max_seq_len: int = 64,
        add_metadata: bool = False,
        metadata: list[dict[str, Any]] | None = None,
        metadata_tokenizer: MetadataTokenizer | None = None,
    ):
        self.passwords = passwords
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len
        self.add_metadata = add_metadata
        self.metadata = metadata or []
        # Real per-example breach-context metadata, tokenized with a shared
        # MetadataTokenizer so IDs are consistent across the whole dataset
        # (and can be persisted/restored via the model checkpoint).
        self.metadata_tokenizer = metadata_tokenizer
        if self.add_metadata and metadata_tokenizer is None:
            raise ValueError("metadata_tokenizer is required when add_metadata=True")
        if self.add_metadata and self.metadata and len(self.metadata) != len(self.passwords):
            raise ValueError(
                f"metadata length ({len(self.metadata)}) must match passwords length ({len(self.passwords)})"
            )

    def __len__(self) -> int:
        return len(self.passwords)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        password = self.passwords[idx]
        encoded = self.tokenizer.encode(password, add_special_tokens=True)

        # Create input/target pairs for next-token prediction
        input_ids = encoded[:-1]
        target_ids = encoded[1:]

        # Pad to max_seq_len
        if len(input_ids) < self.max_seq_len:
            pad_len = self.max_seq_len - len(input_ids)
            input_ids += [self.tokenizer.pad_token_id] * pad_len
            target_ids += [self.tokenizer.pad_token_id] * pad_len
        else:
            input_ids = input_ids[: self.max_seq_len]
            target_ids = target_ids[: self.max_seq_len]

        item = {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "target_ids": torch.tensor(target_ids, dtype=torch.long),
            "attention_mask": torch.tensor(
                [1 if id_ != self.tokenizer.pad_token_id else 0 for id_ in input_ids],
                dtype=torch.long,
            ),
        }

        if self.add_metadata and self.metadata_tokenizer is not None:
            # Real per-example breach context (organization/year/known_leaks/...),
            # tokenized so the model's MetadataEncoder can learn to condition on
            # it. Falls back to an empty-but-valid encoding (just [CLS]+[PAD]s)
            # when this example has no metadata, distinct from a literal zero
            # vector so "explicitly no context" is still a learned signal.
            md = self.metadata[idx] if idx < len(self.metadata) else {}
            meta_ids = self.metadata_tokenizer.encode_metadata(md)
            item["metadata_ids"] = torch.tensor(meta_ids, dtype=torch.long)

        return item


def load_password_list(path: str | Path, max_samples: int | None = None) -> list[str]:
    """Load passwords from a text file (one per line)."""
    passwords = []
    with open(path) as f:
        for line in f:
            pwd = line.strip()
            if pwd:
                passwords.append(pwd)
                if max_samples and len(passwords) >= max_samples:
                    break
    return passwords


def load_rockyou(path: str | Path, max_samples: int | None = None) -> list[str]:
    """Load RockYou dataset (handles encoding issues)."""
    passwords = []
    try:
        with open(path, encoding="latin-1") as f:
            for line in f:
                pwd = line.strip()
                if pwd:
                    passwords.append(pwd)
                    if max_samples and len(passwords) >= max_samples:
                        break
    except UnicodeDecodeError:
        # Fallback - read as binary and decode
        with open(path, "rb") as f:
            for line_bytes in f:
                pwd = line_bytes.decode("latin-1", errors="ignore").strip()
                if pwd:
                    passwords.append(pwd)
                    if max_samples and len(passwords) >= max_samples:
                        break
    return passwords


def create_data_loaders(
    train_passwords: list[str],
    val_passwords: list[str] | None = None,
    tokenizer: PasswordTokenizer | None = None,
    batch_size: int = 32,
    max_seq_len: int = 64,
    num_workers: int = 4,
    val_split: float = 0.1,
    train_metadata: list[dict[str, Any]] | None = None,
    val_metadata: list[dict[str, Any]] | None = None,
    metadata_tokenizer: MetadataTokenizer | None = None,
) -> tuple[DataLoader, DataLoader | None]:
    """Create train and validation data loaders.

    When `train_metadata` is provided (one dict per password, same order/length
    as `train_passwords`), it is carried through the train/val split and shuffle
    in lockstep with its password (metadata must never end up paired with the
    wrong password), and each batch gets a `metadata_ids` tensor the trainer can
    feed through `model.encode_metadata()` for real context conditioning.
    """
    if tokenizer is None:
        tokenizer = PasswordTokenizer(max_seq_len=max_seq_len)

    has_metadata = train_metadata is not None
    if train_metadata is not None and len(train_metadata) != len(train_passwords):
        raise ValueError(
            f"train_metadata length ({len(train_metadata)}) must match "
            f"train_passwords length ({len(train_passwords)})"
        )

    if val_passwords is None:
        # Split training data, shuffling passwords and metadata together via
        # a shared index permutation so pairs never desync.
        indices = list(range(len(train_passwords)))
        random.shuffle(indices)
        train_passwords = [train_passwords[i] for i in indices]
        if train_metadata is not None:
            train_metadata = [train_metadata[i] for i in indices]

        split_idx = int(len(train_passwords) * (1 - val_split))
        val_passwords = train_passwords[split_idx:]
        train_passwords = train_passwords[:split_idx]
        if train_metadata is not None:
            val_metadata = train_metadata[split_idx:]
            train_metadata = train_metadata[:split_idx]

    train_dataset = PasswordDataset(
        train_passwords,
        tokenizer,
        max_seq_len,
        add_metadata=has_metadata,
        metadata=train_metadata,
        metadata_tokenizer=metadata_tokenizer,
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True,
    )

    val_loader = None
    if val_passwords:
        val_dataset = PasswordDataset(
            val_passwords,
            tokenizer,
            max_seq_len,
            add_metadata=has_metadata,
            metadata=val_metadata,
            metadata_tokenizer=metadata_tokenizer,
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=True,
        )

    return train_loader, val_loader


def generate_synthetic_metadata(num_samples: int = 1000) -> list[dict[str, Any]]:
    """Generate synthetic breach metadata for training."""
    orgs = [
        "TechCorp",
        "FinanceInc",
        "HealthNet",
        "EduSystems",
        "GovAgency",
        "RetailCo",
        "MediaGroup",
    ]
    industries = [
        "technology",
        "finance",
        "healthcare",
        "education",
        "government",
        "retail",
        "media",
    ]
    locations = ["US", "EU", "UK", "CA", "AU", "JP", "BR"]
    base_leaks = [
        ["admin", "password", "123456"],
        ["welcome", "qwerty", "letmein"],
        ["company", "secret", "access"],
        ["user", "login", "pass"],
    ]

    metadata = []
    for _ in range(num_samples):
        org = random.choice(orgs)
        metadata.append(
            {
                "organization": org,
                "year": random.randint(2020, 2026),
                "industry": random.choice(industries),
                "location": random.choice(locations),
                "known_leaks": random.choice(base_leaks),
                "employee_count": random.randint(100, 10000),
            }
        )
    return metadata
