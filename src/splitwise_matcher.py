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


def apply_matches(
    transactions: list[dict],
    matches: list[dict],
    splitwise_expenses: list[dict],
    my_user_id: int,
) -> list[dict]:
    """
    Apply Splitwise match data to card transactions.

    For each matched card transaction, attaches:
    - splitwise_matched: True
    - splitwise_owed: my owed_share
    - splitwise_others_owe: paid_share - owed_share

    Args:
        transactions: Card transactions (will not be mutated).
        matches: List of match dicts with splitwise_id and card_transaction_id.
        splitwise_expenses: The "i_paid_shared" expenses from Splitwise cache.
        my_user_id: Splitwise user ID.

    Returns:
        New list of transactions with match data attached where applicable.
    """
    # Build lookup: card_transaction_id -> splitwise_id
    card_to_sw = {}
    for match in matches:
        card_to_sw[match["card_transaction_id"]] = match["splitwise_id"]

    # Build lookup: splitwise_id -> expense
    sw_by_id = {exp["id"]: exp for exp in splitwise_expenses}

    result = []
    for txn in transactions:
        txn_id = generate_transaction_id(txn)
        txn_copy = {**txn}

        if txn_id in card_to_sw:
            sw_id = card_to_sw[txn_id]
            sw_exp = sw_by_id.get(sw_id)

            if sw_exp:
                # Find my share
                for user_entry in sw_exp.get("users", []):
                    if user_entry.get("user_id") == my_user_id:
                        paid = float(user_entry.get("paid_share", "0"))
                        owed = float(user_entry.get("owed_share", "0"))
                        txn_copy["splitwise_matched"] = True
                        txn_copy["splitwise_owed"] = owed
                        txn_copy["splitwise_others_owe"] = paid - owed
                        break

        result.append(txn_copy)

    return result


def run_interactive_matching(
    splitwise_shared: list[dict],
    card_transactions: list[dict],
    match_file: Optional[Path] = None,
) -> list[dict]:
    """
    Run an interactive CLI session to match Splitwise expenses to card transactions.

    For each unmatched Splitwise expense, shows top 3 card transaction candidates
    and prompts the user to pick one.

    Args:
        splitwise_shared: "i_paid_shared" expenses from Splitwise.
        card_transactions: All card transactions.
        match_file: Path to the match persistence file.

    Returns:
        Updated list of all matches (existing + new).
    """
    matches = load_matches(match_file)

    # Build sets of already-matched IDs
    matched_sw_ids = {m["splitwise_id"] for m in matches}
    matched_card_ids = {m["card_transaction_id"] for m in matches}

    # Filter to unmatched Splitwise expenses
    unmatched_sw = [e for e in splitwise_shared if e["id"] not in matched_sw_ids]

    if not unmatched_sw:
        print("No unmatched Splitwise expenses to process.")
        return matches

    # Filter out already-matched card transactions
    available_cards = [
        t for t in card_transactions
        if generate_transaction_id(t) not in matched_card_ids
    ]

    print(f"\n{len(unmatched_sw)} Splitwise expense(s) to match.\n")

    for i, sw_exp in enumerate(unmatched_sw, 1):
        cost = sw_exp.get("cost", "?")
        desc = sw_exp.get("description", "?")
        date = sw_exp.get("date", "?")[:10]

        print(f"--- [{i}/{len(unmatched_sw)}] Splitwise: {desc} | ${cost} | {date} ---")

        candidates = rank_candidates(sw_exp, available_cards)

        if not candidates:
            print("  No candidates found.")
            choice = input("  [s]kip / [n]ot on card / [q]uit: ").strip().lower()
            if choice == "q":
                break
            if choice == "n":
                matches.append(
                    {
                        "splitwise_id": sw_exp["id"],
                        "card_transaction_id": "__not_on_card__",
                        "matched_at": datetime.now().isoformat(),
                    }
                )
            continue

        for j, cand in enumerate(candidates, 1):
            t = cand["txn"]
            score = cand["score"]
            print(
                f"  {j}. {t['description']} | ${t['amount']:.2f} | {t['date']} "
                f"| {t.get('source_display', t.get('source', '?'))} "
                f"[score: {score:.0f}]"
            )

        print(f"  0. None of these")
        print(f"  n. Not on card (Venmo/cash)")
        print(f"  q. Quit matching")

        choice = input("  Pick: ").strip().lower()

        if choice == "q":
            break
        elif choice == "n":
            # Record as "not on card" so we don't ask again
            matches.append(
                {
                    "splitwise_id": sw_exp["id"],
                    "card_transaction_id": "__not_on_card__",
                    "matched_at": datetime.now().isoformat(),
                }
            )
        elif choice == "0":
            continue  # Skip, will ask again next time
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(candidates):
                    matched_txn = candidates[idx]["txn"]
                    card_id = generate_transaction_id(matched_txn)
                    matches.append(
                        {
                            "splitwise_id": sw_exp["id"],
                            "card_transaction_id": card_id,
                            "matched_at": datetime.now().isoformat(),
                        }
                    )
                    # Remove from available pool
                    available_cards = [
                        t for t in available_cards
                        if generate_transaction_id(t) != card_id
                    ]
                    print(f"  Matched!")
                else:
                    print("  Invalid choice, skipping.")
            except ValueError:
                print("  Invalid choice, skipping.")

    save_matches(matches, match_file)
    new_count = len(matches) - len(matched_sw_ids)
    print(f"\nDone. {new_count} new match(es) saved. Total: {len(matches)}.")
    return matches
