"""Tests for formatter with Splitwise match integration."""

import pytest
from src.formatter import Formatter


class TestSplitwiseFormatting:
    """Test that matched transactions get adjusted amounts in export."""

    def test_matched_transaction_uses_splitwise_amounts(self):
        """A matched card txn should show owed_share in 'Amount I owe'."""
        formatter = Formatter()
        transactions = [
            {
                "date": "2026-01-17",
                "description": "WHOLE FOODS MARKET",
                "amount": 82.30,
                "is_credit": False,
                "source": "amex_bcp",
                "source_display": "Amex BCP",
                "category": "Groceries",
                "splitwise_matched": True,
                "splitwise_owed": 41.15,
                "splitwise_others_owe": 41.15,
            }
        ]
        df = formatter.format_transactions(transactions)
        row = df.iloc[0]
        assert row["Amount I owe"] == 41.15
        assert row["Other people Owe me"] == 41.15

    def test_unmatched_transaction_unchanged(self):
        """An unmatched txn should have full amount in 'Amount I owe'."""
        formatter = Formatter()
        transactions = [
            {
                "date": "2026-01-16",
                "description": "UBER TRIP",
                "amount": 18.75,
                "is_credit": False,
                "source": "chase_sapphire",
                "source_display": "Chase Sapphire",
                "category": "Transport",
            }
        ]
        df = formatter.format_transactions(transactions)
        row = df.iloc[0]
        assert row["Amount I owe"] == 18.75

    def test_splitwise_source_shows_as_payment_type(self):
        """Splitwise-sourced transactions should show 'Splitwise' as payment type."""
        formatter = Formatter()
        transactions = [
            {
                "date": "2026-01-20",
                "description": "Dinner at Thai place",
                "amount": 30.00,
                "is_credit": False,
                "source": "splitwise",
                "source_display": "Splitwise",
                "category": "Restaurant",
            }
        ]
        df = formatter.format_transactions(transactions)
        assert df.iloc[0]["Payment Type"] == "Splitwise"
