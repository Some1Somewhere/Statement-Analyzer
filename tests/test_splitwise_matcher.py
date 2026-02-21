"""Tests for Splitwise matcher — ID generation and match persistence."""

import json
import pytest
from pathlib import Path

from src.splitwise_matcher import (
    generate_transaction_id,
    load_matches,
    save_matches,
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
