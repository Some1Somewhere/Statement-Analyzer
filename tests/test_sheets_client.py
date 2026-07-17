"""Tests for the Sheet dedup logic (pure diff, no network)."""

from src.sheets_client import diff_new_rows, _norm_amount, _norm_date


HEADER = [
    "Date", "Month", "Category", "Item", "Payment Type",
    "Amount Charged", "Other people Owe me", "Amount I owe", "Notes",
]


def _sheet_row(date, item, card, amount, **extra):
    row = {
        "Date": date, "Month": "", "Category": "", "Item": item,
        "Payment Type": card, "Amount Charged": amount,
        "Other people Owe me": "", "Amount I owe": "", "Notes": "",
    }
    row.update(extra)
    return [row[c] for c in HEADER]


def _candidate(date, item, card, amount):
    return {
        "Date": date, "Month": "June", "Category": "Misc", "Item": item,
        "Payment Type": card, "Amount Charged": amount,
        "Other people Owe me": "", "Amount I owe": amount, "Notes": "",
    }


class TestNormalizers:
    def test_norm_date_handles_both_sheet_formats(self):
        assert _norm_date("8/1/2024") == "2024-08-01"
        assert _norm_date("2026-06-27") == "2026-06-27"

    def test_norm_amount_strips_currency_formatting(self):
        assert _norm_amount("$6,602.49") == "6602.49"
        assert _norm_amount(23.5) == "23.50"
        assert _norm_amount("") == ""


class TestDiffNewRows:
    def test_new_row_is_appended(self):
        existing = [HEADER, _sheet_row("2026-06-01", "OLD PLACE", "Amex", "10.00")]
        cands = [_candidate("2026-06-02", "NEW PLACE", "Amex", 20.0)]
        assert diff_new_rows(existing, cands) == cands

    def test_existing_row_is_skipped_despite_format_differences(self):
        """Sheet has $-formatted amount and M/D/YYYY date; export has ISO/float."""
        existing = [HEADER, _sheet_row("6/1/2026", "Bonchon Chicken", "BILT", "$43.54")]
        cands = [_candidate("2026-06-01", "bonchon chicken", "BILT", 43.54)]
        assert diff_new_rows(existing, cands) == []

    def test_count_aware_duplicates(self):
        """Sheet holds 2 identical charges, export has 3 -> append only 1."""
        row = _sheet_row("2026-06-05", "OurBus", "Discover", "25.00")
        existing = [HEADER, row, list(row)]
        cands = [_candidate("2026-06-05", "OurBus", "Discover", 25.0) for _ in range(3)]
        assert len(diff_new_rows(existing, cands)) == 1

    def test_edited_title_matches_via_fallback_key(self):
        """User renamed the Item in the sheet (??? flag) — amount key catches it."""
        existing = [HEADER, _sheet_row("2026-06-10", "??? no idea", "Amex", "99.99")]
        cands = [_candidate("2026-06-10", "SOME MERCHANT LLC", "Amex", 99.99)]
        assert diff_new_rows(existing, cands) == []

    def test_blank_sheet_rows_ignored(self):
        existing = [HEADER, ["", "", "", "", "", "", "", "", ""]]
        cands = [_candidate("2026-06-02", "NEW PLACE", "Amex", 20.0)]
        assert len(diff_new_rows(existing, cands)) == 1

    def test_empty_sheet_appends_everything(self):
        cands = [_candidate("2026-06-02", "NEW PLACE", "Amex", 20.0)]
        assert diff_new_rows([], cands) == cands


class TestPlanSplitFills:
    def _cand(self, date, item, card, amount, owe, i_owe):
        return {
            "Date": date, "Month": "", "Category": "", "Item": item,
            "Payment Type": card, "Amount Charged": amount,
            "Other people Owe me": owe, "Amount I owe": i_owe, "Notes": "",
        }

    def test_blank_cell_gets_filled_from_matched_export_row(self):
        from src.sheets_client import plan_split_fills
        existing = [HEADER, _sheet_row("2026-05-10", "URBAN TANDOOR HARRISON NJ",
                                       "Discover", "216.24")]
        cands = [self._cand("2026-05-10", "URBAN TANDOOR HARRISON NJ",
                            "Discover", 216.24, 187.4, 28.84)]
        updates = plan_split_fills(existing, cands)
        assert (2, "Other people Owe me", 187.4) in updates
        assert (2, "Amount I owe", 28.84) in updates

    def test_non_blank_cell_is_never_touched(self):
        from src.sheets_client import plan_split_fills
        row = _sheet_row("2026-05-10", "URBAN TANDOOR HARRISON NJ",
                         "Discover", "216.24")
        row[HEADER.index("Other people Owe me")] = "50.00"
        cands = [self._cand("2026-05-10", "URBAN TANDOOR HARRISON NJ",
                            "Discover", 216.24, 187.4, 28.84)]
        assert plan_split_fills([HEADER, row], cands) == []

    def test_candidate_without_split_does_not_fill(self):
        from src.sheets_client import plan_split_fills
        existing = [HEADER, _sheet_row("2026-05-10", "SOME PLACE", "Amex", "20.00")]
        cands = [self._cand("2026-05-10", "SOME PLACE", "Amex", 20.0, "", 20.0)]
        assert plan_split_fills(existing, cands) == []

    def test_solo_zero_fills_blank(self):
        from src.sheets_client import plan_split_fills
        existing = [HEADER, _sheet_row("2026-05-04", "MTA*NYCT PAYGO", "Chase", "3.00")]
        cands = [self._cand("2026-05-04", "MTA*NYCT PAYGO", "Chase", 3.0, 0, 3.0)]
        updates = plan_split_fills(existing, cands)
        assert (2, "Other people Owe me", 0) in updates

    def test_one_candidate_fills_only_one_row(self):
        from src.sheets_client import plan_split_fills
        row = _sheet_row("2026-05-10", "OurBus", "Discover", "25.00")
        existing = [HEADER, row, list(row)]
        cands = [self._cand("2026-05-10", "OurBus", "Discover", 25.0, 12.5, 12.5)]
        updates = plan_split_fills(existing, cands)
        assert len({rn for rn, _, _ in updates}) == 1

    def test_same_day_same_merchant_different_amounts_never_cross_fill(self):
        """Regression: three same-day WAL-MART charges; the split belongs to
        the $141.32 one and must not land on the $44.11 or $65.14 rows."""
        from src.sheets_client import plan_split_fills
        existing = [
            HEADER,
            _sheet_row("2026-06-19", "WAL-MART", "Robinhood Gold", "44.11"),
            _sheet_row("2026-06-19", "WAL-MART", "Robinhood Gold", "65.14"),
            _sheet_row("2026-06-19", "WAL-MART", "Robinhood Gold", "141.32"),
        ]
        cands = [self._cand("2026-06-19", "WAL-MART", "Robinhood Gold",
                            141.32, 165.33, 20.67)]
        updates = plan_split_fills(existing, cands)
        rows_touched = {rn for rn, _, _ in updates}
        assert rows_touched == {4}  # only the 141.32 row (row 4 of the sheet)
