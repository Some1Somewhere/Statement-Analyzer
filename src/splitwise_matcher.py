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


def rank_candidates(
    splitwise_expense: dict,
    card_transactions: list[dict],
    top_n: int = 3,
) -> list[dict]:
    """
    Rank card transactions as candidates for matching a Splitwise expense.

    Scoring:
    - Date proximity: max 50 points, loses 10 per day of distance
    - Amount similarity: max 50 points, loses proportionally to % difference

    Args:
        splitwise_expense: A Splitwise expense dict with "cost" and "date".
        card_transactions: List of card transaction dicts.
        top_n: Number of top candidates to return.

    Returns:
        List of {"txn": card_txn, "score": float} sorted by score descending.
    """
    sw_cost = float(splitwise_expense.get("cost", "0"))
    sw_date_str = splitwise_expense.get("date", "")
    try:
        sw_date = datetime.fromisoformat(sw_date_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return []

    scored = []
    for txn in card_transactions:
        # Skip credits
        if txn.get("is_credit", False):
            continue

        # Date score: max 50, lose 10 per day
        try:
            txn_date = datetime.strptime(txn.get("date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        day_diff = abs((txn_date - sw_date).days)
        date_score = max(0, 50 - day_diff * 10)

        # Amount score: max 50, proportional to closeness
        txn_amount = txn.get("amount", 0)
        if sw_cost > 0:
            pct_diff = abs(txn_amount - sw_cost) / sw_cost
            amount_score = max(0, 50 - pct_diff * 100)
        else:
            amount_score = 0

        total_score = date_score + amount_score
        if total_score > 0:
            scored.append({"txn": txn, "score": total_score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]
