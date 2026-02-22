"""Splitwise API client for fetching and classifying shared expenses."""

import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import SPLITWISE_API_KEY, SPLITWISE_BASE_URL, INTERMEDIATE_DIR


class SplitwiseClient:
    """Client for interacting with the Splitwise API."""

    def __init__(self):
        """Initialize the Splitwise client with API key."""
        if not SPLITWISE_API_KEY:
            raise ValueError(
                "SPLITWISE_API_KEY not found. Please set it in your .env file."
            )
        self.api_key = SPLITWISE_API_KEY
        self.base_url = SPLITWISE_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def get_current_user(self) -> dict:
        """Get the current authenticated user's info."""
        resp = self.session.get(f"{self.base_url}/get_current_user")
        resp.raise_for_status()
        return resp.json()["user"]

    def get_expenses(
        self,
        dated_after: Optional[str] = None,
        dated_before: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch all expenses with pagination.

        Args:
            dated_after: ISO datetime string (e.g., "2026-01-01T00:00:00Z")
            dated_before: ISO datetime string
            limit: Results per page (max varies by API)

        Returns:
            List of all expense dicts from the API.
        """
        all_expenses = []
        offset = 0

        while True:
            params = {"limit": limit, "offset": offset}
            if dated_after:
                params["dated_after"] = dated_after
            if dated_before:
                params["dated_before"] = dated_before

            resp = self.session.get(
                f"{self.base_url}/get_expenses", params=params
            )
            resp.raise_for_status()
            expenses = resp.json().get("expenses", [])

            if not expenses:
                break

            all_expenses.extend(expenses)
            offset += limit

            if len(expenses) < limit:
                break

        return all_expenses

    def fetch_and_cache(
        self,
        dated_after: Optional[str] = None,
        dated_before: Optional[str] = None,
    ) -> dict:
        """
        Fetch expenses, classify them, and cache to intermediate JSON.

        Returns:
            Dict with user_id and classified expenses.
        """
        user = self.get_current_user()
        my_user_id = user["id"]
        print(f"Authenticated as: {user['first_name']} {user['last_name']}")

        expenses = self.get_expenses(dated_after, dated_before)
        print(f"Fetched {len(expenses)} expenses from Splitwise")

        classified = self.classify_expenses(expenses, my_user_id)
        print(
            f"  Others paid: {len(classified['others_paid'])}, "
            f"I paid shared: {len(classified['i_paid_shared'])}, "
            f"I paid solo: {len(classified['i_paid_solo'])}"
        )

        # Cache to intermediate
        cache_data = {
            "user_id": my_user_id,
            "fetched_at": datetime.now().isoformat(),
            "others_paid": classified["others_paid"],
            "i_paid_shared": classified["i_paid_shared"],
            "i_paid_solo": classified["i_paid_solo"],
        }
        cache_path = INTERMEDIATE_DIR / "splitwise_expenses.json"
        INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
        print(f"  Cached to: {cache_path.name}")

        return cache_data

    @staticmethod
    def classify_expenses(expenses: list[dict], my_user_id: int) -> dict:
        """
        Classify expenses based on the current user's share.

        Args:
            expenses: Raw expense dicts from the Splitwise API.
            my_user_id: The authenticated user's Splitwise user ID.

        Returns:
            Dict with keys: others_paid, i_paid_shared, i_paid_solo
        """
        result = {"others_paid": [], "i_paid_shared": [], "i_paid_solo": []}

        for expense in expenses:
            # Skip payments (settling up)
            if expense.get("payment", False):
                continue

            # Skip deleted expenses
            if expense.get("deleted_at"):
                continue

            # Skip non-USD expenses
            if expense.get("currency_code", "USD") != "USD":
                continue

            # Skip debt consolidation ("Settle all balances") — internal Splitwise bookkeeping
            if expense.get("creation_method") == "debt_consolidation":
                continue

            # Find the current user's share
            my_share = None
            for user_entry in expense.get("users", []):
                if user_entry.get("user_id") == my_user_id:
                    my_share = user_entry
                    break

            if my_share is None:
                continue

            paid = float(my_share.get("paid_share", "0"))
            owed = float(my_share.get("owed_share", "0"))

            if paid == 0 and owed > 0:
                result["others_paid"].append(expense)
            elif paid > 0 and owed < paid:
                result["i_paid_shared"].append(expense)
            elif paid > 0 and owed >= paid:
                result["i_paid_solo"].append(expense)

        return result

    @staticmethod
    def to_transactions(expenses: list[dict], my_user_id: int) -> list[dict]:
        """
        Convert Splitwise expenses to transaction dicts matching the card format.

        Used for "others_paid" expenses to inject into the export pipeline.

        Args:
            expenses: List of classified Splitwise expense dicts.
            my_user_id: The authenticated user's Splitwise user ID.

        Returns:
            List of transaction dicts with date, description, amount, etc.
        """
        transactions = []

        for expense in expenses:
            # Find my owed share
            owed_share = 0.0
            for user_entry in expense.get("users", []):
                if user_entry.get("user_id") == my_user_id:
                    owed_share = float(user_entry.get("owed_share", "0"))
                    break

            # Parse date to YYYY-MM-DD
            date_str = expense.get("date", "")
            try:
                date_obj = datetime.fromisoformat(
                    date_str.replace("Z", "+00:00")
                )
                date_formatted = date_obj.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_formatted = date_str[:10] if len(date_str) >= 10 else ""

            transactions.append(
                {
                    "date": date_formatted,
                    "description": expense.get("description", ""),
                    "amount": owed_share,
                    "is_credit": False,
                    "source": "splitwise",
                    "source_display": "Splitwise",
                    "statement_file": "",
                    "splitwise_id": expense.get("id"),
                }
            )

        return transactions

    @staticmethod
    def load_cached() -> Optional[dict]:
        """Load cached Splitwise data from intermediate file."""
        cache_path = INTERMEDIATE_DIR / "splitwise_expenses.json"
        if not cache_path.exists():
            return None
        with open(cache_path) as f:
            return json.load(f)
