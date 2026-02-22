"""Tests for Splitwise client expense classification."""

import pytest
from src.splitwise_client import SplitwiseClient


class TestClassifyExpenses:
    """Test classify_expenses with different expense types."""

    def test_others_paid_expense(self, sample_splitwise_expenses):
        """Expense where someone else paid and I owe -> others_paid."""
        my_user_id = 1
        # expense 1002: user 2 paid 60, I owe 30
        result = SplitwiseClient.classify_expenses(
            sample_splitwise_expenses, my_user_id
        )
        others_paid = result["others_paid"]
        assert len(others_paid) == 1
        assert others_paid[0]["id"] == 1002

    def test_i_paid_shared_expense(self, sample_splitwise_expenses):
        """Expense where I paid and it's split -> i_paid_shared."""
        my_user_id = 1
        # expense 1001: I paid 82.30, I owe 41.15
        result = SplitwiseClient.classify_expenses(
            sample_splitwise_expenses, my_user_id
        )
        i_paid_shared = result["i_paid_shared"]
        assert len(i_paid_shared) == 1
        assert i_paid_shared[0]["id"] == 1001

    def test_payment_skipped(self, sample_splitwise_expenses):
        """Payment/settle-up expenses should be skipped."""
        my_user_id = 1
        result = SplitwiseClient.classify_expenses(
            sample_splitwise_expenses, my_user_id
        )
        # Payment (id 1003) should not appear in any category
        all_ids = (
            [e["id"] for e in result["others_paid"]]
            + [e["id"] for e in result["i_paid_shared"]]
            + [e["id"] for e in result["i_paid_solo"]]
        )
        assert 1003 not in all_ids

    def test_i_paid_solo_expense(self):
        """Expense where I paid the full amount and owe the full amount -> skip."""
        expenses = [
            {
                "id": 2001,
                "cost": "25.00",
                "description": "Solo lunch",
                "date": "2026-01-15T12:00:00Z",
                "payment": False,
                "currency_code": "USD",
                "category": {"id": 13, "name": "Dining out"},
                "group_id": 100,
                "users": [
                    {"user_id": 1, "paid_share": "25.00", "owed_share": "25.00"},
                ],
            }
        ]
        result = SplitwiseClient.classify_expenses(expenses, my_user_id=1)
        assert len(result["i_paid_solo"]) == 1
        assert len(result["others_paid"]) == 0
        assert len(result["i_paid_shared"]) == 0


    def test_non_usd_expenses_filtered(self):
        """Non-USD expenses should be skipped during classification."""
        expenses = [
            {
                "id": 3001,
                "cost": "229.0",
                "description": "Spotify premium",
                "date": "2026-02-12T18:12:21Z",
                "payment": False,
                "currency_code": "INR",
                "users": [
                    {"user_id": 2, "paid_share": "229.0", "owed_share": "114.5"},
                    {"user_id": 1, "paid_share": "0.0", "owed_share": "114.5"},
                ],
            },
            {
                "id": 3002,
                "cost": "50.00",
                "description": "Lunch",
                "date": "2026-02-12T12:00:00Z",
                "payment": False,
                "currency_code": "USD",
                "users": [
                    {"user_id": 2, "paid_share": "50.00", "owed_share": "25.00"},
                    {"user_id": 1, "paid_share": "0.0", "owed_share": "25.00"},
                ],
            },
        ]
        result = SplitwiseClient.classify_expenses(expenses, my_user_id=1)
        # Only the USD expense should appear
        assert len(result["others_paid"]) == 1
        assert result["others_paid"][0]["id"] == 3002


    def test_debt_consolidation_filtered(self):
        """Settle all balances (debt_consolidation) should be skipped."""
        expenses = [
            {
                "id": 4001,
                "cost": "36.25",
                "description": "Settle all balances",
                "date": "2026-01-15T12:00:00Z",
                "payment": False,
                "currency_code": "USD",
                "creation_method": "debt_consolidation",
                "users": [
                    {"user_id": 2, "paid_share": "36.25", "owed_share": "0.00"},
                    {"user_id": 1, "paid_share": "0.00", "owed_share": "36.25"},
                ],
            },
        ]
        result = SplitwiseClient.classify_expenses(expenses, my_user_id=1)
        assert len(result["others_paid"]) == 0
        assert len(result["i_paid_shared"]) == 0
        assert len(result["i_paid_solo"]) == 0


class TestConvertToTransactions:
    """Test converting Splitwise expenses to transaction format."""

    def test_others_paid_to_transaction(self, sample_splitwise_expenses):
        """Others_paid expense converts to transaction with owed_share as amount."""
        my_user_id = 1
        classified = SplitwiseClient.classify_expenses(
            sample_splitwise_expenses, my_user_id
        )
        transactions = SplitwiseClient.to_transactions(
            classified["others_paid"], my_user_id
        )
        assert len(transactions) == 1
        txn = transactions[0]
        assert txn["date"] == "2026-01-20"
        assert txn["description"] == "Dinner at Thai place"
        assert txn["amount"] == 30.00
        assert txn["is_credit"] is False
        assert txn["source"] == "splitwise"
        assert txn["source_display"] == "Splitwise"
        assert txn["splitwise_id"] == 1002
