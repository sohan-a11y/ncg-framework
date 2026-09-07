"""Synthetic password dataset generator mimicking real-world password distributions.

Creates passwords following empirically-observed patterns from leaked-password
research (RockYou-style): common bases + digits/specials appended, leetspeak
substitutions, keyboard walks, and organization-contextual patterns.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

# Common password bases (top patterns from RockYou analyses)
COMMON_BASES = [
    "password", "123456", "12345678", "qwerty", "abc123", "monkey", "letmein",
    "dragon", "111111", "baseball", "iloveyou", "trustno1", "sunshine",
    "master", "welcome", "shadow", "ashley", "football", "michael", "ninja",
    "mustang", "password1", "admin", "root", "guest", "test", "user",
    "login", "pass", "secret", "qazwsx", "killer", "superman", "hunter",
    "soccer", "batman", "whatever", "access", "love", "hello", "freedom",
]

# Common appendages: years, digits, specials
YEARS = [str(y) for y in range(1970, 2031)]
DIGITS = ["1", "12", "123", "1234", "12345", "123456", "7", "13", "21", "42", "69", "99", "007"]
SPECIALS = ["!", "@", "#", "$", "%", "?", "*", ".", "~", "!!", "!1", "@1"]

# Common leetspeak substitutions
LEET_MAP = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7", "l": "1", "g": "9"}

# Keyboard walks
KEYBOARD_WALKS = [
    "qwerty", "asdfgh", "zxcvbn", "qazwsx", "1qaz2wsx", "qwertyuiop",
    "asdfghjkl", "zxcvbnm", "1q2w3e4r", "qwaszx", "poiuyt", "lkjhgf",
    "azeazy", "qwertz", "1234qwer", "147258369", "159753", "741852963",
]

# Organization name components for contextual passwords
ORG_TEMPLATES = [
    "{org}", "{org}123", "{org}2024", "{org}2025", "{org}2026", "{org}!",
    "{Org}", "{ORG}", "{org}admin", "admin{org}", "{org}pass", "{org}pw",
    "{org}#1", "{org}rocks", "{org}01", "{org}123!", "Ilove{org}", "{org}4ever",
    "{org}@2026", "{org}security", "{org}login", "{org}mypass", "{org}2026!",
]

# Word combinations
WORDS = [
    "love", "cool", "fast", "big", "the", "my", "hot", "new", "top", "pro",
    "super", "mega", "ultra", "cyber", "tech", "data", "code", "net", "web",
    "info", "sys", "dev", "ops", "cloud", "dark", "zero", "one", "prime",
]


def apply_leet(text: str, probability: float = 0.3) -> str:
    """Apply random leetspeak substitutions to text."""
    if random.random() > probability:
        return text
    result = []
    for ch in text:
        if ch.lower() in LEET_MAP and random.random() < 0.4:
            result.append(LEET_MAP[ch.lower()])
        else:
            result.append(ch)
    return "".join(result)


def capitalize_variant(text: str) -> str:
    """Apply a random capitalization variant."""
    r = random.random()
    if r < 0.3:
        return text.capitalize()
    elif r < 0.4:
        return text.upper()
    elif r < 0.5:
        return text[:1].upper() + text[1:].upper() if len(text) > 1 else text.upper()
    return text


def generate_common_base_password() -> str:
    """Generate password from common base + appendage pattern (most common real pattern)."""
    base = random.choice(COMMON_BASES)
    r = random.random()
    if r < 0.3:
        return base
    elif r < 0.5:
        return base + random.choice(YEARS)
    elif r < 0.7:
        return base + random.choice(DIGITS)
    elif r < 0.85:
        return base + random.choice(SPECIALS)
    else:
        return base + random.choice(DIGITS) + random.choice(SPECIALS)


def generate_word_password() -> str:
    """Generate password from word combinations."""
    word1 = random.choice(WORDS)
    r = random.random()
    if r < 0.3:
        word2 = random.choice(WORDS)
        pwd = word1 + word2
    elif r < 0.5:
        pwd = word1 + random.choice(YEARS)
    else:
        pwd = word1
    pwd = capitalize_variant(pwd)
    if random.random() < 0.3:
        pwd += random.choice(DIGITS + SPECIALS)
    return pwd


def generate_keyboard_password() -> str:
    """Generate keyboard-walk password."""
    walk = random.choice(KEYBOARD_WALKS)
    r = random.random()
    if r < 0.4:
        return walk
    elif r < 0.7:
        return walk + random.choice(DIGITS)
    return capitalize_variant(walk)


def generate_contextual_password(org: str) -> str:
    """Generate organization-contextual password (the key NCG innovation)."""
    template = random.choice(ORG_TEMPLATES)
    pwd = template.format(org=org.lower(), Org=org.capitalize(), ORG=org.upper())
    if random.random() < 0.2:
        pwd = apply_leet(pwd)
    return pwd


def generate_password(org: str = "TechCorp") -> str:
    """Generate a single password following realistic distribution.

    Distribution roughly matches leaked-password research:
    - 45% common base + appendage
    - 20% contextual (org name)
    - 15% word combos
    - 10% keyboard walks
    - 10% leetspeak variants
    """
    r = random.random()
    if r < 0.45:
        pwd = generate_common_base_password()
    elif r < 0.65:
        pwd = generate_contextual_password(org)
    elif r < 0.80:
        pwd = generate_word_password()
    elif r < 0.90:
        pwd = generate_keyboard_password()
    else:
        base = random.choice(COMMON_BASES + WORDS)
        pwd = apply_leet(base, probability=0.9)
        if random.random() < 0.5:
            pwd += random.choice(DIGITS)
    # Length filter: keep 6-20 chars (realistic)
    if len(pwd) < 6:
        pwd += random.choice(DIGITS)
    return pwd[:20]


def generate_dataset(num_passwords: int, org: str = "TechCorp", seed: int = 42) -> list[str]:
    """Generate a full dataset with realistic password distribution."""
    random.seed(seed)
    return [generate_password(org) for _ in range(num_passwords)]


def generate_multi_org_dataset(
    num_per_org: int, orgs: list[str], seed: int = 42
) -> tuple[list[str], list[dict]]:
    """Generate a labeled dataset spanning multiple organizations.

    Unlike generate_dataset() (a single org for the whole file), this pairs
    each password with its {"organization": org} breach context so a model
    can actually be trained to distinguish contexts -- generate_dataset()
    alone gives a model no signal to learn organization-conditioning from,
    since every example shares the same (single) context.

    Returns (passwords, metadata) with matching order/length; the two lists
    are shuffled together (never desynced) so downstream consumers can split
    train/val simply by slicing both the same way.
    """
    random.seed(seed)
    passwords: list[str] = []
    metadata: list[dict] = []
    for org in orgs:
        for _ in range(num_per_org):
            passwords.append(generate_password(org))
            metadata.append({"organization": org})

    combined = list(zip(passwords, metadata, strict=True))
    random.shuffle(combined)
    passwords, metadata = (list(t) for t in zip(*combined, strict=True))
    return passwords, metadata


def save_dataset_jsonl(passwords: list[str], metadata: list[dict], path: str | Path) -> None:
    """Save a (password, metadata) dataset as JSON Lines, one {"password", "metadata"} per line."""
    if len(passwords) != len(metadata):
        raise ValueError(f"passwords ({len(passwords)}) and metadata ({len(metadata)}) length mismatch")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for pwd, meta in zip(passwords, metadata, strict=True):
            f.write(json.dumps({"password": pwd, "metadata": meta}) + "\n")
    logger.info("Saved %d contextual passwords to %s", len(passwords), path)


def load_dataset_jsonl(path: str | Path) -> tuple[list[str], list[dict]]:
    """Load a (password, metadata) dataset saved by save_dataset_jsonl()."""
    passwords: list[str] = []
    metadata: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            passwords.append(row["password"])
            metadata.append(row.get("metadata", {}))
    return passwords, metadata


def is_jsonl_dataset(path: str | Path) -> bool:
    """Detect whether a dataset file is JSONL (password+metadata) vs plain text."""
    path = Path(path)
    if path.suffix == ".jsonl":
        return True
    try:
        with open(path, encoding="utf-8") as f:
            first_line = f.readline().strip()
        if not first_line:
            return False
        row = json.loads(first_line)
        return isinstance(row, dict) and "password" in row
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return False


def save_dataset(passwords: list[str], path: str | Path) -> None:
    """Save passwords to file (one per line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(passwords))
    logger.info("Saved %d passwords to %s", len(passwords), path)


def save_dataset_json(passwords: list[str], path: str | Path, org: str = "TechCorp") -> None:
    """Save dataset with metadata in JSON format."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "metadata": {
            "org": org,
            "count": len(passwords),
            "description": "Synthetic password dataset with realistic distribution",
            "patterns": [
                "common_base_appendage (45%)",
                "contextual_org (20%)",
                "word_combinations (15%)",
                "keyboard_walks (10%)",
                "leetspeak (10%)",
            ],
        },
        "passwords": passwords,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Saved %d passwords to %s", len(passwords), path)


def generate_holdout_set(num: int = 100, seed: int = 999) -> list[str]:
    """Generate a holdout set for evaluating top-k accuracy."""
    random.seed(seed)
    return [generate_password("TechCorp") for _ in range(num)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic password dataset")
    parser.add_argument("--num", "-n", type=int, default=10000, help="Number of passwords")
    parser.add_argument("--org", default="TechCorp", help="Organization name for context")
    parser.add_argument("--output", "-o", default="data/passwords.txt", help="Output file")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    passwords = generate_dataset(args.num, args.org, args.seed)
    save_dataset(passwords, args.output)

    # Print sample -- standalone-script output, not library code, so print()
    # (not logging) is the right tool here.
    print("\nSample passwords:")  # noqa: T201
    for pwd in passwords[:10]:
        print(f"  {pwd}")  # noqa: T201
