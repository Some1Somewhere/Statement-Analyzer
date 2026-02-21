"""Splitwise matcher — match card transactions to Splitwise shared expenses."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import SPLITWISE_MATCHES_FILE


def generate_transaction_id(txn: dict) -> str:
    """
    Generate a deterministic ID for a card transaction.

    Built from source + statement_file + date + description + amount.
    Stable across re-runs since the same PDF always extracts the same data.
    """
    parts = [
        txn.get("source", ""),
        txn.get("statement_file", ""),
        txn.get("date", ""),
        txn.get("description", ""),
        str(txn.get("amount", 0)),
    ]
    return "|".join(parts)


def load_matches(match_file: Optional[Path] = None) -> list[dict]:
    """Load confirmed matches from JSON file."""
    path = match_file or SPLITWISE_MATCHES_FILE
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_matches(matches: list[dict], match_file: Optional[Path] = None):
    """Save confirmed matches to JSON file."""
    path = match_file or SPLITWISE_MATCHES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(matches, f, indent=2)
