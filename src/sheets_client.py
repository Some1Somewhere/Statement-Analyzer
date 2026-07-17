"""Google Sheets client — push export results into the manually-curated Sheet.

The Sheet (``Main`` tab) is the source of truth: the user reconciles rows by
hand (fills "Other people Owe me", flags unknowns with ???). Pushes must be
purely additive — existing rows are never edited or removed.

Dedup is by matching, not by cutoff or hidden id column:
- Primary key:  (date, item, payment type)
- Fallback key: (date, payment type, amount) — survives titles the user
  edited in the Sheet (e.g. "???" flags).
Keys are count-aware (a Counter, not a set) because genuine duplicate
charges exist (same merchant, same day, same card, several rows); only the
excess beyond what the Sheet already holds is appended.
"""

import re
from collections import defaultdict, deque
from datetime import datetime

import gspread

from .config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SHEET_ID,
    OUTPUT_COLUMNS,
    SHEET_TAB,
)

UNMATCHED_TAB = "Unmatched Splitwise"
UNMATCHED_HEADER = [
    "Date", "Description", "Total Cost", "You Paid",
    "Your Share", "Others Owe You", "Splitwise ID",
]

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y")


def _norm_date(value: str) -> str:
    """Normalize sheet/tool date strings to ISO. Unparseable -> as-is."""
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def _norm_text(value: str) -> str:
    """Lowercase and collapse whitespace for key comparison."""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _norm_amount(value) -> str:
    """Normalize '$1,234.5' / 1234.5 / '1234.50' to '1234.50'. Bad -> ''."""
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return ""


def diff_new_rows(existing_values: list[list[str]], candidates: list[dict]) -> list[dict]:
    """
    Return the candidate rows not already present in the sheet.

    existing_values: raw worksheet values, first row is the header.
    candidates: dicts keyed by OUTPUT_COLUMNS.

    Count-aware: each existing sheet row can absorb exactly one candidate,
    via its (date, item, card) primary key or its (date, card, amount)
    fallback key — never both. Genuine duplicate charges therefore only
    append the excess beyond what the sheet already holds.
    """
    if not existing_values:
        existing_values = [OUTPUT_COLUMNS]

    header = existing_values[0]
    col_idx = {name: i for i, name in enumerate(header)}

    def cell(row: list[str], name: str) -> str:
        idx = col_idx.get(name)
        if idx is None or idx >= len(row):
            return ""
        return row[idx]

    # Each existing row is one consumable unit, indexed under both its keys.
    # Consuming it through either key removes it from both indexes.
    primary_index: dict = defaultdict(deque)   # pkey -> deque of fkeys
    fallback_index: dict = defaultdict(deque)  # fkey -> deque of pkeys
    for row in existing_values[1:]:
        if not any(str(c).strip() for c in row):
            continue
        date = _norm_date(cell(row, "Date"))
        item = _norm_text(cell(row, "Item"))
        card = _norm_text(cell(row, "Payment Type"))
        amount = _norm_amount(cell(row, "Amount Charged"))
        pkey = (date, item, card)
        fkey = (date, card, amount)
        primary_index[pkey].append(fkey)
        fallback_index[fkey].append(pkey)

    new_rows = []
    for cand in candidates:
        date = _norm_date(str(cand.get("Date", "")))
        item = _norm_text(cand.get("Item", ""))
        card = _norm_text(cand.get("Payment Type", ""))
        amount = _norm_amount(cand.get("Amount Charged", ""))

        pkey = (date, item, card)
        fkey = (date, card, amount)
        if primary_index[pkey]:
            used_fkey = primary_index[pkey].popleft()
            fallback_index[used_fkey].remove(pkey)
        elif fallback_index[fkey]:
            used_pkey = fallback_index[fkey].popleft()
            primary_index[used_pkey].remove(fkey)
        else:
            new_rows.append(cand)

    return new_rows


def plan_split_fills(
    existing_values: list[list[str]], candidates: list[dict]
) -> list[tuple[int, str, object]]:
    """
    Plan updates for existing sheet rows whose "Other people Owe me" is blank
    but whose matching export row has a value (Splitwise split or solo 0).

    Blank means "not yet determined", so filling it completes the row;
    non-blank cells are the user's reconciliation and are never touched.
    "Amount I owe" is updated alongside so the row's math stays consistent.

    Unlike append-dedup, every key here REQUIRES an exact amount: transferring
    split values onto a row that merely shares date/title/card is how money
    lands on the wrong one of several same-day same-merchant charges. A row
    whose amount matches nothing is left alone.

    Returns a list of (1-based row number, column name, new value).
    """
    if not existing_values:
        return []

    header = existing_values[0]
    col_idx = {name: i for i, name in enumerate(header)}
    owe_idx = col_idx.get("Other people Owe me")
    if owe_idx is None:
        return []

    def cell(row: list[str], name: str) -> str:
        idx = col_idx.get(name)
        if idx is None or idx >= len(row):
            return ""
        return row[idx]

    def keys(date, item, card, amount):
        # Amount is in BOTH keys — see docstring.
        return (date, item, card, amount), (date, card, amount)

    # Index candidates that actually carry a split value, under both keys.
    by_pkey: dict = defaultdict(deque)
    by_fkey: dict = defaultdict(deque)
    for cand in candidates:
        if str(cand.get("Other people Owe me", "")).strip() == "":
            continue
        pkey, fkey = keys(
            _norm_date(str(cand.get("Date", ""))),
            _norm_text(cand.get("Item", "")),
            _norm_text(cand.get("Payment Type", "")),
            _norm_amount(cand.get("Amount Charged", "")),
        )
        by_pkey[pkey].append(cand)
        by_fkey[fkey].append(cand)

    updates = []
    for row_num, row in enumerate(existing_values[1:], start=2):
        if owe_idx < len(row) and str(row[owe_idx]).strip() != "":
            continue  # already reconciled — hands off
        if not any(str(c).strip() for c in row):
            continue
        pkey, fkey = keys(
            _norm_date(cell(row, "Date")),
            _norm_text(cell(row, "Item")),
            _norm_text(cell(row, "Payment Type")),
            _norm_amount(cell(row, "Amount Charged")),
        )
        if by_pkey.get(pkey):
            cand = by_pkey[pkey].popleft()
            consumed_via_pkey = True
        elif by_fkey.get(fkey):
            cand = by_fkey[fkey].popleft()
            consumed_via_pkey = False
        else:
            continue
        # Remove from the sibling index so one candidate fills one row.
        cand_pkey, cand_fkey = keys(
            _norm_date(str(cand.get("Date", ""))),
            _norm_text(cand.get("Item", "")),
            _norm_text(cand.get("Payment Type", "")),
            _norm_amount(cand.get("Amount Charged", "")),
        )
        sibling = by_fkey[cand_fkey] if consumed_via_pkey else by_pkey[cand_pkey]
        if cand in sibling:
            sibling.remove(cand)
        updates.append((row_num, "Other people Owe me", cand["Other people Owe me"]))
        updates.append((row_num, "Amount I owe", cand.get("Amount I owe", "")))

    return updates


class SheetsClient:
    """Thin gspread wrapper for the expense Sheet."""

    def __init__(self):
        if not GOOGLE_SHEET_ID:
            raise ValueError("GOOGLE_SHEET_ID is not set in .env")
        if not GOOGLE_SERVICE_ACCOUNT_FILE.exists():
            raise ValueError(
                f"Service account file not found: {GOOGLE_SERVICE_ACCOUNT_FILE}"
            )
        gc = gspread.service_account(filename=str(GOOGLE_SERVICE_ACCOUNT_FILE))
        self.spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)

    def _get_or_create_tab(self, title: str, header: list[str]):
        try:
            ws = self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title, rows=1000, cols=len(header))
            ws.append_row(header)
        return ws

    def find_new_expenses(self, rows: list[dict]) -> list[dict]:
        """Return the rows not already present in the expenses tab."""
        ws = self._get_or_create_tab(SHEET_TAB, OUTPUT_COLUMNS)
        return diff_new_rows(ws.get_all_values(), rows)

    def append_expenses(self, rows: list[dict]) -> int:
        """
        Append expense rows that are not already in the Sheet.

        Existing rows are never touched, so manual edits and ??? flags persist.
        Returns the number of rows appended.
        """
        ws = self._get_or_create_tab(SHEET_TAB, OUTPUT_COLUMNS)
        new_rows = diff_new_rows(ws.get_all_values(), rows)
        if new_rows:
            values = [
                [row.get(col, "") for col in OUTPUT_COLUMNS] for row in new_rows
            ]
            ws.append_rows(values, value_input_option="USER_ENTERED")
        return len(new_rows)

    def find_split_fills(self, rows: list[dict]) -> list[tuple[int, str, object]]:
        """Preview which blank split cells would be filled (dry run)."""
        ws = self._get_or_create_tab(SHEET_TAB, OUTPUT_COLUMNS)
        return plan_split_fills(ws.get_all_values(), rows)

    def fill_blank_splits(self, rows: list[dict]) -> int:
        """
        Fill blank "Other people Owe me" (and matching "Amount I owe") cells
        on existing rows from export rows that carry split values.

        Never overwrites a non-blank cell. Returns the number of rows updated.
        """
        ws = self._get_or_create_tab(SHEET_TAB, OUTPUT_COLUMNS)
        values = ws.get_all_values()
        updates = plan_split_fills(values, rows)
        if not updates:
            return 0
        header = values[0]
        # ponytail: A-Z column letters only; header has 9 columns.
        col_letter = {name: chr(ord("A") + i) for i, name in enumerate(header)}
        data = [
            {"range": f"{col_letter[col]}{row_num}", "values": [[value]]}
            for row_num, col, value in updates
        ]
        ws.batch_update(data, value_input_option="USER_ENTERED")
        return len({row_num for row_num, _, _ in updates})

    def replace_unmatched(self, rows: list[dict]) -> int:
        """Replace the Unmatched Splitwise tab contents. Returns row count."""
        ws = self._get_or_create_tab(UNMATCHED_TAB, UNMATCHED_HEADER)
        ws.clear()
        values = [UNMATCHED_HEADER] + [
            [row.get(col, "") for col in UNMATCHED_HEADER] for row in rows
        ]
        ws.update(values, value_input_option="USER_ENTERED")
        return len(rows)
