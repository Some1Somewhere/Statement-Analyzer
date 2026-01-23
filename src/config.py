"""Configuration and constants for the Statement Analyzer."""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Model names
GEMINI_FLASH_MODEL = "gemini-2.0-flash-exp"
GEMINI_PRO_MODEL = "gemini-1.5-pro"

# Directory paths
BASE_DIR = Path(__file__).parent.parent
STATEMENTS_DIR = BASE_DIR / "statements"
DATA_DIR = BASE_DIR / "data"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
OUTPUT_DIR = BASE_DIR / "output"
CATEGORIES_FILE = DATA_DIR / "categories.json"
CARDS_FILE = DATA_DIR / "cards.json"


def _load_card_types() -> dict:
    """Load card types from JSON config file."""
    if CARDS_FILE.exists():
        with open(CARDS_FILE) as f:
            return json.load(f)
    else:
        # Fallback to example if no config exists
        example_file = DATA_DIR / "cards.example.json"
        if example_file.exists():
            with open(example_file) as f:
                return json.load(f)
        return {}


# Supported card types and their display names (loaded from config)
CARD_TYPES = _load_card_types()

# Categories for expense classification
CATEGORIES = [
    "Health",
    "Rent",
    "Restaurant",
    "Transport",
    "Misc",
    "Groceries",
    "Work",
    "Entertainment",
    "Household",
    "Gift",
    "Intoxicants",
    "Vacations",
    "Dates",
]

# Default category when no match is found
DEFAULT_CATEGORY = "UNKNOWN"

# CSV output columns
OUTPUT_COLUMNS = [
    "Date",
    "Month",
    "Category",
    "Item",
    "Payment Type",
    "Amount Charged",
    "Other people Owe me",
    "Amount I owe",
    "Notes",
]
