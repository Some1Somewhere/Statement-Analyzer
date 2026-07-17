"""Splitwise matcher — match card transactions to Splitwise shared expenses."""

import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import SPLITWISE_MATCHES_FILE, OUTPUT_DIR


# Stop tokens that add no signal when comparing Splitwise descriptions
# (free-form, written by humans) against card merchant strings.
_DESC_STOP_TOKENS = frozenset({
    "the", "at", "on", "in", "and", "or", "with", "for", "to", "a", "an",
    "of", "my", "our", "your", "from", "is", "was", "by",
})


def _tokenize_description(text: str) -> set[str]:
    """Lowercase, extract alphanumeric tokens, drop 1-char and stop tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 1 and t not in _DESC_STOP_TOKENS}


def _description_score(sw_desc: str, card_desc: str, max_score: float) -> float:
    """
    Score description similarity by shared-token overlap coefficient.

    Uses |shared| / |smaller set| rather than Jaccard so card descriptions
    with chaff like store locations ("BOHO KARAOKE WEST 4TH") are not
    penalised for noise the user did not type into Splitwise.
    """
    if not sw_desc or not card_desc:
        return 0.0
    sw_tokens = _tokenize_description(sw_desc)
    card_tokens = _tokenize_description(card_desc)
    if not sw_tokens or not card_tokens:
        return 0.0
    overlap = sw_tokens & card_tokens
    if not overlap:
        return 0.0
    smaller = min(len(sw_tokens), len(card_tokens))
    return max_score * (len(overlap) / smaller)


def generate_transaction_id(txn: dict, *, include_index: bool = True) -> str:
    """
    Generate a deterministic ID for a card transaction.

    Built from source + statement_file + date + description + amount, plus the
    transaction's position within its source file (``file_index``) when
    available. The positional tiebreaker disambiguates genuine duplicate
    charges (e.g. two identical same-day Uber trips on one statement) that
    would otherwise collapse to the same ID and cross-apply a single match.

    ``include_index=False`` reproduces the legacy ID format (no ``file_index``).
    Lookups try the current ID first and fall back to the legacy ID, so matches
    saved before the tiebreaker was introduced still resolve — only true
    duplicate charges ever need re-matching.

    Stable across re-runs since the same PDF always extracts the same data in
    the same order.
    """
    parts = [
        txn.get("source", ""),
        txn.get("statement_file", ""),
        txn.get("date", ""),
        txn.get("description", ""),
        str(txn.get("amount", 0)),
    ]
    if include_index and "file_index" in txn:
        parts.append(str(txn["file_index"]))
    return "|".join(parts)


def load_matches(match_file: Optional[Path] = None) -> list[dict]:
    """Load confirmed matches from JSON file."""
    path = match_file or SPLITWISE_MATCHES_FILE
    if not path.exists():
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        # Matches are hand-built user work that cannot be regenerated from the
        # API, so fail loudly rather than silently discarding the file.
        raise ValueError(
            f"Match file is corrupt ({path}). Fix or delete it to start fresh. ({e})"
        ) from e


def save_matches(matches: list[dict], match_file: Optional[Path] = None):
    """Save confirmed matches to JSON file."""
    path = match_file or SPLITWISE_MATCHES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(matches, f, indent=2)


def rank_candidates(
    splitwise_expense: dict,
    card_transactions: list[dict],
    top_n: int = 5,
    my_user_id: Optional[int] = None,
) -> list[dict]:
    """
    Rank card transactions as candidates for matching a Splitwise expense.

    Scoring (max 100):
    - Amount similarity: max 50 points, decays at 1 per % difference.
      Compares against paid_share (what you actually paid) rather than cost
      (total bill), since your card shows what you paid. Strongest single
      signal — an exact dollar match is rare-by-coincidence.
    - Description similarity: max 30 points (merchant-token overlap).
      A real tiebreaker — "Boho Karaoke" → "BOHO KARAOKE WEST 4TH" should
      beat a closer-date but unrelated transaction.
    - Date proximity: max 20 points, loses 1 per day (20-day window).
      Softer than the previous 10-day cliff because Splitwise expenses are
      often logged days or weeks after the card actually posted.

    Args:
        splitwise_expense: A Splitwise expense dict with "cost", "date", "users".
        card_transactions: List of card transaction dicts.
        top_n: Number of top candidates to return.
        my_user_id: Splitwise user ID to look up paid_share. Falls back to cost.

    Returns:
        List of {"txn": card_txn, "score": float} sorted by score descending.
    """
    # Use paid_share if available (what appears on the card), fall back to cost
    match_amount = float(splitwise_expense.get("cost", "0"))
    if my_user_id:
        for user_entry in splitwise_expense.get("users", []):
            if user_entry.get("user_id") == my_user_id:
                paid = float(user_entry.get("paid_share", "0"))
                if paid > 0:
                    match_amount = paid
                break

    sw_date_str = splitwise_expense.get("date", "")
    try:
        sw_date = datetime.fromisoformat(sw_date_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return []

    sw_desc = splitwise_expense.get("description", "")

    scored = []
    for txn in card_transactions:
        # Skip credits
        if txn.get("is_credit", False):
            continue

        # Date score: max 20, lose 1/day (covers 20-day window)
        try:
            txn_date = datetime.strptime(txn.get("date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        day_diff = abs((txn_date - sw_date).days)
        date_score = max(0, 20 - day_diff)

        # Amount score: max 50, proportional to closeness (zeroes at 50% off)
        txn_amount = txn.get("amount", 0)
        if match_amount > 0:
            pct_diff = abs(txn_amount - match_amount) / match_amount
            amount_score = max(0, 50 - pct_diff * 100)
        else:
            amount_score = 0

        # Description score: max 30, token-overlap coefficient
        desc_score = _description_score(sw_desc, txn.get("description", ""), 30)

        total_score = date_score + amount_score + desc_score
        if total_score > 0:
            scored.append({"txn": txn, "score": total_score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def _share_amounts(sw_exp: dict, my_user_id: Optional[int]) -> tuple:
    """Return (owed_share, others_owe) for my_user_id in a Splitwise expense."""
    for user_entry in sw_exp.get("users", []):
        if user_entry.get("user_id") == my_user_id:
            paid = float(user_entry.get("paid_share", "0"))
            owed = float(user_entry.get("owed_share", "0"))
            return owed, round(paid - owed, 2)
    return None, None


def _dedupe_matches(matches: list[dict]) -> list[dict]:
    """Drop exact duplicate (splitwise_id, card_transaction_id) pairs."""
    seen = set()
    unique = []
    for m in matches:
        pair = (m["splitwise_id"], m["card_transaction_id"])
        if pair not in seen:
            seen.add(pair)
            unique.append(m)
    return unique


def _match_amounts(match: dict, sw_by_id: dict, my_user_id: int) -> tuple:
    """
    Resolve (owed_share, others_owe) for a match.

    Prefers amounts stored on the match record itself (self-contained, survives
    cache refetches); falls back to looking up the expense in the cache for
    legacy matches saved before amounts were stored.
    """
    if "owed_share" in match and "others_owe" in match:
        return float(match["owed_share"]), float(match["others_owe"])
    sw_exp = sw_by_id.get(match["splitwise_id"])
    if sw_exp is None:
        return None, None
    return _share_amounts(sw_exp, my_user_id)


def backfill_match_amounts(
    matches: list[dict], splitwise_expenses: list[dict], my_user_id: int
) -> int:
    """
    Store owed_share/others_owe on legacy match records that lack them,
    using expenses currently in the cache. Mutates matches in place.

    Returns the number of records updated.
    """
    sw_by_id = {exp["id"]: exp for exp in splitwise_expenses}
    updated = 0
    for match in matches:
        if match["card_transaction_id"] == "__not_on_card__":
            continue
        if "owed_share" in match and "others_owe" in match:
            continue
        sw_exp = sw_by_id.get(match["splitwise_id"])
        if sw_exp is None:
            continue
        owed, others = _share_amounts(sw_exp, my_user_id)
        if owed is None:
            continue
        match["owed_share"] = owed
        match["others_owe"] = others
        updated += 1
    return updated


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

    When one Splitwise expense is matched to N card transactions (a single
    Splitwise entry covering several charges), both amounts are divided evenly
    across the N rows so the total across rows equals the expense.

    Amounts come from the match record itself when stored there; the cache
    lookup is only a fallback for legacy matches.

    Args:
        transactions: Card transactions (will not be mutated).
        matches: List of match dicts with splitwise_id and card_transaction_id.
        splitwise_expenses: The "i_paid_shared" expenses from Splitwise cache.
        my_user_id: Splitwise user ID.

    Returns:
        New list of transactions with match data attached where applicable.
    """
    unique_matches = _dedupe_matches(matches)

    # card_transaction_id -> match record, and per-expense match counts for
    # dividing amounts across multi-row matches.
    card_to_match = {
        m["card_transaction_id"]: m
        for m in unique_matches
        if m["card_transaction_id"] != "__not_on_card__"
    }
    group_size = Counter(m["splitwise_id"] for m in card_to_match.values())

    sw_by_id = {exp["id"]: exp for exp in splitwise_expenses}

    result = []
    for txn in transactions:
        # Try the current id, then the legacy id (no file_index) so matches
        # saved before the tiebreaker was added still resolve.
        match = card_to_match.get(generate_transaction_id(txn))
        if match is None:
            match = card_to_match.get(
                generate_transaction_id(txn, include_index=False)
            )
        txn_copy = {**txn}

        if match is not None:
            owed, others = _match_amounts(match, sw_by_id, my_user_id)
            if owed is None:
                print(
                    f"Warning: no amounts for Splitwise expense "
                    f"{match['splitwise_id']} (not in cache, none stored); "
                    f"leaving '{txn.get('description', '')}' unsplit. "
                    f"Re-run fetch-splitwise with a wider --days to backfill."
                )
            else:
                # ponytail: even split rounded to cents; up to n-1 cents of
                # drift per group, proportional split if it ever matters.
                n = group_size[match["splitwise_id"]] or 1
                txn_copy["splitwise_matched"] = True
                txn_copy["splitwise_owed"] = round(owed / n, 2)
                txn_copy["splitwise_others_owe"] = round(others / n, 2)

        result.append(txn_copy)

    return result


def run_interactive_matching(
    splitwise_shared: list[dict],
    card_transactions: list[dict],
    my_user_id: Optional[int] = None,
    match_file: Optional[Path] = None,
) -> list[dict]:
    """
    Run an interactive CLI session to match Splitwise expenses to card transactions.

    For each unmatched Splitwise expense, shows top candidates ranked by
    date/amount similarity and prompts the user to pick one.

    Args:
        splitwise_shared: "i_paid_shared" expenses from Splitwise.
        card_transactions: All card transactions.
        my_user_id: Splitwise user ID (for paid_share lookup in ranking).
        match_file: Path to the match persistence file.

    Returns:
        Updated list of all matches (existing + new).
    """
    matches = load_matches(match_file)
    initial_count = len(matches)

    # Build sets of already-matched IDs
    matched_sw_ids = {m["splitwise_id"] for m in matches}
    matched_card_ids = {m["card_transaction_id"] for m in matches}

    # Filter to unmatched Splitwise expenses
    unmatched_sw = [e for e in splitwise_shared if e["id"] not in matched_sw_ids]

    if not unmatched_sw:
        print("No unmatched Splitwise expenses to process.")
        return matches

    # Filter out already-matched card transactions (check both the current and
    # legacy id so cards matched before the tiebreaker change stay matched).
    available_cards = [
        t for t in card_transactions
        if generate_transaction_id(t) not in matched_card_ids
        and generate_transaction_id(t, include_index=False) not in matched_card_ids
    ]

    print(f"\n{len(unmatched_sw)} Splitwise expense(s) to match.\n")

    for i, sw_exp in enumerate(unmatched_sw, 1):
        cost = sw_exp.get("cost", "?")
        desc = sw_exp.get("description", "?")
        date = sw_exp.get("date", "?")[:10]

        # Show paid_share if different from cost
        paid_str = ""
        if my_user_id:
            for u in sw_exp.get("users", []):
                if u.get("user_id") == my_user_id:
                    paid = float(u.get("paid_share", "0"))
                    if abs(paid - float(cost)) > 0.01:
                        paid_str = f" (you paid: ${paid:.2f})"
                    break

        print(f"--- [{i}/{len(unmatched_sw)}] Splitwise: {desc} | ${cost}{paid_str} | {date} ---")

        candidates = rank_candidates(sw_exp, available_cards, my_user_id=my_user_id)

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

        print("  0. None of these")
        print("  n. Not on card (Venmo/cash)")
        print("  q. Quit matching")

        choice = input("  Pick (comma-separate to match multiple rows): ").strip().lower()

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
                idxs = sorted({int(p) - 1 for p in choice.split(",")})
            except ValueError:
                print("  Invalid choice, skipping.")
                continue
            if not all(0 <= idx < len(candidates) for idx in idxs):
                print("  Invalid choice, skipping.")
                continue

            # Store split amounts on the match so it survives cache refetches.
            owed, others = _share_amounts(sw_exp, my_user_id)
            matched_card_ids_now = []
            for idx in idxs:
                matched_txn = candidates[idx]["txn"]
                card_id = generate_transaction_id(matched_txn)
                record = {
                    "splitwise_id": sw_exp["id"],
                    "card_transaction_id": card_id,
                    "matched_at": datetime.now().isoformat(),
                }
                if owed is not None:
                    record["owed_share"] = owed
                    record["others_owe"] = others
                matches.append(record)
                matched_card_ids_now.append(card_id)

            # Remove from available pool
            available_cards = [
                t for t in available_cards
                if generate_transaction_id(t) not in matched_card_ids_now
            ]
            print(f"  Matched {len(idxs)} row(s)!")

    save_matches(matches, match_file)
    new_count = len(matches) - initial_count
    print(f"\nDone. {new_count} new match(es) saved. Total: {len(matches)}.")
    return matches


def export_unmatched_splitwise(
    i_paid_shared: list[dict],
    matches: list[dict],
    my_user_id: int,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Export unmatched Splitwise i_paid_shared expenses to a CSV.

    These are expenses you added to Splitwise (you paid) that have not yet
    been matched to a card transaction or marked as not on card.

    Args:
        i_paid_shared: The "i_paid_shared" expenses from Splitwise cache.
        matches: Current match list.
        my_user_id: Splitwise user ID.
        output_path: Output CSV path. Defaults to output/unmatched_splitwise.csv.

    Returns:
        Path to the written CSV.
    """
    path = output_path or OUTPUT_DIR / "unmatched_splitwise.csv"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    matched_sw_ids = {m["splitwise_id"] for m in matches}
    unmatched = [e for e in i_paid_shared if e["id"] not in matched_sw_ids]

    rows = []
    for e in sorted(unmatched, key=lambda x: x.get("date", "")):
        my_entry = next(
            (u for u in e.get("users", []) if u.get("user_id") == my_user_id),
            None,
        )
        paid = float(my_entry.get("paid_share", "0")) if my_entry else 0.0
        owed = float(my_entry.get("owed_share", "0")) if my_entry else 0.0

        date_str = e.get("date", "")[:10]
        rows.append({
            "Date": date_str,
            "Description": e.get("description", ""),
            "Total Cost": float(e.get("cost", 0)),
            "You Paid": paid,
            "Your Share": owed,
            "Others Owe You": round(paid - owed, 2),
            "Splitwise ID": e["id"],
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "Date", "Description", "Total Cost", "You Paid",
            "Your Share", "Others Owe You", "Splitwise ID",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} unmatched Splitwise expenses to: {path}")
    return path
