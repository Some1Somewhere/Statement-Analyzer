"""Shared test fixtures for Statement Analyzer tests."""

import pytest


@pytest.fixture
def sample_card_transactions():
    """Sample card transactions as returned by PDFExtractor.get_all_transactions()."""
    return [
        {
            "date": "2026-01-15",
            "description": "CHIPOTLE MEXICAN GRILL",
            "amount": 25.50,
            "is_credit": False,
            "source": "chase_sapphire",
            "source_display": "Chase Sapphire",
            "statement_file": "stmt_jan2026.pdf",
        },
        {
            "date": "2026-01-16",
            "description": "UBER TRIP",
            "amount": 18.75,
            "is_credit": False,
            "source": "chase_sapphire",
            "source_display": "Chase Sapphire",
            "statement_file": "stmt_jan2026.pdf",
        },
        {
            "date": "2026-01-17",
            "description": "WHOLE FOODS MARKET",
            "amount": 82.30,
            "is_credit": False,
            "source": "amex_bcp",
            "source_display": "Amex BCP",
            "statement_file": "stmt_jan2026.pdf",
        },
        {
            "date": "2026-01-18",
            "description": "NETFLIX",
            "amount": 15.99,
            "is_credit": False,
            "source": "discover",
            "source_display": "Discover",
            "statement_file": "stmt_jan2026.pdf",
        },
    ]


@pytest.fixture
def sample_splitwise_expenses():
    """Sample raw Splitwise API expense responses."""
    return [
        {
            "id": 1001,
            "cost": "82.30",
            "description": "Whole Foods groceries",
            "date": "2026-01-17T18:00:00Z",
            "payment": False,
            "currency_code": "USD",
            "category": {"id": 12, "name": "Groceries"},
            "group_id": 100,
            "users": [
                {"user_id": 1, "paid_share": "82.30", "owed_share": "41.15"},
                {"user_id": 2, "paid_share": "0.00", "owed_share": "41.15"},
            ],
        },
        {
            "id": 1002,
            "cost": "60.00",
            "description": "Dinner at Thai place",
            "date": "2026-01-20T20:00:00Z",
            "payment": False,
            "currency_code": "USD",
            "category": {"id": 13, "name": "Dining out"},
            "group_id": 100,
            "users": [
                {"user_id": 2, "paid_share": "60.00", "owed_share": "30.00"},
                {"user_id": 1, "paid_share": "0.00", "owed_share": "30.00"},
            ],
        },
        {
            "id": 1003,
            "cost": "50.00",
            "description": "Settle up",
            "date": "2026-01-21T10:00:00Z",
            "payment": True,
            "currency_code": "USD",
            "category": {"id": 18, "name": "Payment"},
            "group_id": 100,
            "users": [
                {"user_id": 1, "paid_share": "50.00", "owed_share": "0.00"},
                {"user_id": 2, "paid_share": "0.00", "owed_share": "50.00"},
            ],
        },
    ]
