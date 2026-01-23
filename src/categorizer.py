"""Transaction categorization module using keyword matching."""

import json
from pathlib import Path
from typing import Optional

from .config import CATEGORIES_FILE, CATEGORIES, DEFAULT_CATEGORY


class Categorizer:
    """Categorize transactions based on keyword matching."""

    def __init__(self, use_gemini_fallback: bool = False):
        """
        Initialize the categorizer.

        Args:
            use_gemini_fallback: Whether to use Gemini Pro for ambiguous items
        """
        self.use_gemini_fallback = use_gemini_fallback
        self.category_keywords = self._load_category_keywords()
        self._gemini_client = None

    def _load_category_keywords(self) -> dict[str, list[str]]:
        """Load category keywords from JSON file."""
        if CATEGORIES_FILE.exists():
            with open(CATEGORIES_FILE) as f:
                return json.load(f)
        else:
            print(f"Warning: {CATEGORIES_FILE} not found. Using empty keywords.")
            return {cat: [] for cat in CATEGORIES}

    def _get_gemini_client(self):
        """Lazy load Gemini client only when needed."""
        if self._gemini_client is None:
            from .gemini_client import GeminiClient
            self._gemini_client = GeminiClient()
        return self._gemini_client

    def categorize(self, description: str, amount: Optional[float] = None) -> str:
        """
        Categorize a transaction based on its description.

        Args:
            description: Transaction description/merchant name
            amount: Transaction amount (optional, used for Gemini fallback)

        Returns:
            Category name from predefined list
        """
        # Normalize description for matching
        desc_lower = description.lower().strip()

        # Try keyword matching first
        category = self._match_keywords(desc_lower)

        if category:
            return category

        # If no match and Gemini fallback is enabled, use AI
        if self.use_gemini_fallback and amount is not None:
            try:
                client = self._get_gemini_client()
                return client.categorize_transaction(description, amount)
            except Exception as e:
                print(f"Gemini fallback failed for '{description}': {e}")

        return DEFAULT_CATEGORY

    def _match_keywords(self, description: str) -> Optional[str]:
        """
        Match description against category keywords.

        Args:
            description: Lowercased transaction description

        Returns:
            Matched category or None
        """
        # Score each category based on keyword matches
        best_category = None
        best_score = 0

        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in description:
                    # Longer keyword matches get higher scores
                    score = len(keyword_lower)
                    if score > best_score:
                        best_score = score
                        best_category = category

        return best_category

    def categorize_transactions(
        self, transactions: list[dict], description_field: str = "description"
    ) -> list[dict]:
        """
        Categorize a list of transactions.

        Args:
            transactions: List of transaction dictionaries
            description_field: Key for the description field

        Returns:
            Transactions with 'category' field added
        """
        categorized = []

        for txn in transactions:
            description = txn.get(description_field, "")
            amount = txn.get("amount", 0)

            category = self.categorize(description, amount)

            categorized_txn = {**txn, "category": category}
            categorized.append(categorized_txn)

        return categorized

    def get_category_stats(self, transactions: list[dict]) -> dict:
        """
        Get statistics about categorized transactions.

        Args:
            transactions: List of categorized transactions

        Returns:
            Dictionary with category counts and amounts
        """
        stats = {cat: {"count": 0, "total": 0.0} for cat in CATEGORIES}

        for txn in transactions:
            category = txn.get("category", DEFAULT_CATEGORY)
            amount = txn.get("amount", 0)

            if category in stats:
                stats[category]["count"] += 1
                stats[category]["total"] += amount

        # Filter out empty categories
        return {cat: data for cat, data in stats.items() if data["count"] > 0}

    def add_keyword(self, category: str, keyword: str) -> bool:
        """
        Add a new keyword to a category.

        Args:
            category: Category name
            keyword: Keyword to add

        Returns:
            True if added successfully
        """
        if category not in CATEGORIES:
            print(f"Unknown category: {category}")
            return False

        if category not in self.category_keywords:
            self.category_keywords[category] = []

        keyword_lower = keyword.lower()
        if keyword_lower not in [k.lower() for k in self.category_keywords[category]]:
            self.category_keywords[category].append(keyword)
            self._save_keywords()
            return True

        return False

    def _save_keywords(self):
        """Save updated keywords to JSON file."""
        with open(CATEGORIES_FILE, "w") as f:
            json.dump(self.category_keywords, f, indent=2)


