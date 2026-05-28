"""Tests for Splitwise matcher — ID generation and match persistence."""

import pytest

from src.splitwise_matcher import (
    generate_transaction_id,
    load_matches,
    save_matches,
    rank_candidates,
    apply_matches,
)


class TestGenerateTransactionId:
    """Test deterministic transaction ID generation."""

    def test_basic_id_generation(self):
        txn = {
            "source": "chase_sapphire",
            "statement_file": "stmt_jan2026.pdf",
            "date": "2026-01-15",
            "description": "CHIPOTLE MEXICAN GRILL",
            "amount": 25.50,
        }
        tid = generate_transaction_id(txn)
        assert tid == "chase_sapphire|stmt_jan2026.pdf|2026-01-15|CHIPOTLE MEXICAN GRILL|25.5"

    def test_same_input_same_id(self):
        txn = {
            "source": "amex_bcp",
            "statement_file": "stmt.pdf",
            "date": "2026-02-01",
            "description": "WHOLE FOODS",
            "amount": 50.00,
        }
        assert generate_transaction_id(txn) == generate_transaction_id(txn)

    def test_different_amount_different_id(self):
        base = {
            "source": "chase_sapphire",
            "statement_file": "stmt.pdf",
            "date": "2026-01-15",
            "description": "CHIPOTLE",
        }
        txn_a = {**base, "amount": 25.50}
        txn_b = {**base, "amount": 30.00}
        assert generate_transaction_id(txn_a) != generate_transaction_id(txn_b)

    def test_duplicate_charges_disambiguated_by_file_index(self):
        """Two identical same-day charges must get distinct ids via file_index."""
        base = {
            "source": "chase_sapphire",
            "statement_file": "stmt.pdf",
            "date": "2026-01-15",
            "description": "UBER TRIP",
            "amount": 4.50,
        }
        first = {**base, "file_index": 0}
        second = {**base, "file_index": 1}
        assert generate_transaction_id(first) != generate_transaction_id(second)


class TestMatchPersistence:
    """Test loading and saving match files."""

    def test_load_empty_when_no_file(self, tmp_path):
        matches = load_matches(tmp_path / "nonexistent.json")
        assert matches == []

    def test_save_and_load_roundtrip(self, tmp_path):
        match_file = tmp_path / "matches.json"
        matches = [
            {
                "splitwise_id": 1001,
                "card_transaction_id": "chase|stmt.pdf|2026-01-15|CHIPOTLE|25.5",
                "matched_at": "2026-02-21T10:00:00",
            }
        ]
        save_matches(matches, match_file)
        loaded = load_matches(match_file)
        assert loaded == matches

    def test_save_overwrites(self, tmp_path):
        match_file = tmp_path / "matches.json"
        save_matches([{"splitwise_id": 1}], match_file)
        save_matches([{"splitwise_id": 2}], match_file)
        loaded = load_matches(match_file)
        assert len(loaded) == 1
        assert loaded[0]["splitwise_id"] == 2


class TestRankCandidates:
    """Test ranking of card transaction candidates for a Splitwise expense."""

    def test_exact_amount_and_close_date_ranked_first(
        self, sample_card_transactions
    ):
        """A card txn with exact amount match and same day should rank highest."""
        sw_expense = {
            "id": 1001,
            "cost": "82.30",
            "date": "2026-01-17T18:00:00Z",
        }
        ranked = rank_candidates(sw_expense, sample_card_transactions)
        # WHOLE FOODS MARKET: same date, same amount
        assert ranked[0]["txn"]["description"] == "WHOLE FOODS MARKET"

    def test_returns_top_n_candidates(self, sample_card_transactions):
        sw_expense = {
            "id": 1001,
            "cost": "82.30",
            "date": "2026-01-17T18:00:00Z",
        }
        ranked = rank_candidates(sw_expense, sample_card_transactions, top_n=2)
        assert len(ranked) <= 2

    def test_score_decreases_with_date_distance(self):
        """Candidates farther in date should score lower."""
        txns = [
            {
                "date": "2026-01-15",
                "description": "A",
                "amount": 50.00,
                "source": "x",
                "statement_file": "s.pdf",
            },
            {
                "date": "2026-01-17",
                "description": "B",
                "amount": 50.00,
                "source": "x",
                "statement_file": "s.pdf",
            },
        ]
        sw = {"id": 1, "cost": "50.00", "date": "2026-01-17T12:00:00Z"}
        ranked = rank_candidates(sw, txns)
        # B is same day, should rank higher than A (2 days away)
        assert ranked[0]["txn"]["description"] == "B"

    def test_empty_transactions_returns_empty(self):
        sw = {"id": 1, "cost": "50.00", "date": "2026-01-17T12:00:00Z"}
        ranked = rank_candidates(sw, [])
        assert ranked == []

    def test_description_match_beats_closer_date_with_no_text_overlap(self):
        """
        Real-world regression: a Splitwise "Beer at Boho Karaoke" logged 12
        days after the actual charge should still rank the BOHO KARAOKE card
        line above a closer-date but text-unrelated bar at a similar amount.
        Before description scoring, the 12-day gap zeroed the date component
        and an unrelated transaction won purely on date proximity.
        """
        sw = {
            "id": 1,
            "cost": "24.02",
            "description": "Beer at Boho Karaoke",
            "date": "2026-04-29T12:00:00Z",
        }
        txns = [
            {
                "date": "2026-05-04",
                "description": "LE PISTOL BROOKLYN NY",
                "amount": 23.20,
                "is_credit": False,
                "source": "discover",
                "statement_file": "stmt.pdf",
            },
            {
                "date": "2026-04-17",
                "description": "BOHO KARAOKE WEST 4TH",
                "amount": 24.02,
                "is_credit": False,
                "source": "robinhood",
                "statement_file": "stmt.pdf",
            },
        ]
        ranked = rank_candidates(sw, txns)
        assert ranked[0]["txn"]["description"] == "BOHO KARAOKE WEST 4TH"

    def test_description_score_ignores_stop_words_and_chaff(self):
        """Shared content words should match even when surrounded by chaff."""
        sw = {
            "id": 1,
            "cost": "50.00",
            "description": "Dinner at the Thai place",
            "date": "2026-01-20T20:00:00Z",
        }
        txns = [
            {
                "date": "2026-01-20",
                "description": "THAI BISTRO NYC",
                "amount": 50.00,
                "is_credit": False,
                "source": "x",
                "statement_file": "s.pdf",
            },
            {
                "date": "2026-01-20",
                "description": "PIZZA PALACE",
                "amount": 50.00,
                "is_credit": False,
                "source": "x",
                "statement_file": "s.pdf",
            },
        ]
        ranked = rank_candidates(sw, txns)
        assert ranked[0]["txn"]["description"] == "THAI BISTRO NYC"


class TestApplyMatches:
    """Test applying Splitwise match data to card transactions."""

    def test_matched_transaction_gets_adjusted_amounts(self):
        """A matched card txn should have splitwise share data attached."""
        transactions = [
            {
                "date": "2026-01-17",
                "description": "WHOLE FOODS MARKET",
                "amount": 82.30,
                "is_credit": False,
                "source": "amex_bcp",
                "statement_file": "stmt.pdf",
            }
        ]
        matches = [
            {
                "splitwise_id": 1001,
                "card_transaction_id": "amex_bcp|stmt.pdf|2026-01-17|WHOLE FOODS MARKET|82.3",
            }
        ]
        sw_expenses = [
            {
                "id": 1001,
                "cost": "82.30",
                "users": [
                    {"user_id": 1, "paid_share": "82.30", "owed_share": "41.15"},
                    {"user_id": 2, "paid_share": "0.00", "owed_share": "41.15"},
                ],
            }
        ]
        result = apply_matches(transactions, matches, sw_expenses, my_user_id=1)
        assert result[0]["splitwise_matched"] is True
        assert result[0]["splitwise_owed"] == 41.15
        assert result[0]["splitwise_others_owe"] == pytest.approx(41.15)

    def test_legacy_match_still_applies_with_file_index_present(self):
        """A match saved in the legacy id format must still resolve once the
        transaction carries a file_index (backward compatibility)."""
        transactions = [
            {
                "date": "2026-01-17",
                "description": "WHOLE FOODS MARKET",
                "amount": 82.30,
                "is_credit": False,
                "source": "amex_bcp",
                "statement_file": "stmt.pdf",
                "file_index": 3,  # present now, absent when the match was saved
            }
        ]
        # Legacy id has no trailing file_index segment.
        matches = [
            {
                "splitwise_id": 1001,
                "card_transaction_id": "amex_bcp|stmt.pdf|2026-01-17|WHOLE FOODS MARKET|82.3",
            }
        ]
        sw_expenses = [
            {
                "id": 1001,
                "cost": "82.30",
                "users": [
                    {"user_id": 1, "paid_share": "82.30", "owed_share": "41.15"},
                ],
            }
        ]
        result = apply_matches(transactions, matches, sw_expenses, my_user_id=1)
        assert result[0]["splitwise_matched"] is True
        assert result[0]["splitwise_owed"] == 41.15

    def test_unmatched_transaction_unchanged(self):
        """An unmatched card txn should pass through with no splitwise fields."""
        transactions = [
            {
                "date": "2026-01-16",
                "description": "UBER TRIP",
                "amount": 18.75,
                "is_credit": False,
                "source": "chase_sapphire",
                "statement_file": "stmt.pdf",
            }
        ]
        result = apply_matches(transactions, [], [], my_user_id=1)
        assert result[0].get("splitwise_matched") is not True
