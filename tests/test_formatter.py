"""Tests for formatter with Splitwise match integration."""

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


class TestSoloExpenseTransitRule:
    """Transit charges are individual expenses — auto-set 'Other people Owe me' to 0."""

    def test_mta_nyct_paygo_is_solo_expense(self):
        """Real MTA tap-to-pay descriptions must flag as solo expenses."""
        formatter = Formatter()
        transactions = [
            {
                "date": "2026-04-10",
                "description": "MTA*NYCT PAYGO NEW YORK NY",
                "amount": 2.90,
                "is_credit": False,
                "source": "amex_bcp",
                "source_display": "Amex BCP",
                "category": "Transport",
            }
        ]
        df = formatter.format_transactions(transactions)
        assert df.iloc[0]["Other people Owe me"] == 0

    def test_path_is_solo_expense(self):
        """PATH (NJ) charges are individual expenses."""
        formatter = Formatter()
        transactions = [
            {
                "date": "2026-04-10",
                "description": "PATH TAPP PAYGO CP NEW JERSEY NJ",
                "amount": 3.00,
                "is_credit": False,
                "source": "amex_bcp",
                "source_display": "Amex BCP",
                "category": "Transport",
            }
        ]
        df = formatter.format_transactions(transactions)
        assert df.iloc[0]["Other people Owe me"] == 0

    def test_lirr_is_solo_expense(self):
        formatter = Formatter()
        transactions = [
            {
                "date": "2026-04-10",
                "description": "MTA*LIRR ETIX TICKET",
                "amount": 12.50,
                "is_credit": False,
                "source": "amex_bcp",
                "source_display": "Amex BCP",
                "category": "Transport",
            }
        ]
        df = formatter.format_transactions(transactions)
        assert df.iloc[0]["Other people Owe me"] == 0

    def test_uber_is_not_auto_solo_expense(self):
        """Non-transit Transport entries (Uber/Lyft) should not auto-zero —
        they're often split rides or expensable separately."""
        formatter = Formatter()
        transactions = [
            {
                "date": "2026-04-10",
                "description": "UBER TRIP HELP.UBER.COM",
                "amount": 18.75,
                "is_credit": False,
                "source": "chase_sapphire",
                "source_display": "Chase Sapphire",
                "category": "Transport",
            }
        ]
        df = formatter.format_transactions(transactions)
        assert df.iloc[0]["Other people Owe me"] == ""


class TestZeroAmountFilter:
    def test_zero_amount_rows_are_dropped(self):
        from src.formatter import Formatter
        txns = [
            {"date": "2026-05-21", "description": "INTEREST CHARGED ON PURCHASES",
             "amount": 0.0, "is_credit": False, "source": "bofa_custom_cash"},
            {"date": "2026-05-21", "description": "REAL CHARGE",
             "amount": 12.5, "is_credit": False, "source": "bofa_custom_cash"},
        ]
        df = Formatter().format_transactions(txns)
        assert len(df) == 1
        assert df.iloc[0]["Item"] == "REAL CHARGE"
