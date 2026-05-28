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
GEMINI_FLASH_MODEL = "gemini-2.5-flash"
GEMINI_PRO_MODEL = "gemini-2.5-pro"

# Directory paths
BASE_DIR = Path(__file__).parent.parent
STATEMENTS_DIR = BASE_DIR / "statements"
DATA_DIR = BASE_DIR / "data"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
OUTPUT_DIR = BASE_DIR / "output"
CATEGORIES_FILE = DATA_DIR / "categories.json"
CARDS_FILE = DATA_DIR / "cards.json"

SPLITWISE_API_KEY = os.getenv("SPLITWISE_API_KEY")
SPLITWISE_BASE_URL = "https://secure.splitwise.com/api/v3.0"
SPLITWISE_MATCHES_FILE = DATA_DIR / "splitwise_matches.json"
# (connect, read) timeouts in seconds for Splitwise HTTP requests
SPLITWISE_REQUEST_TIMEOUT = (10, 30)


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

# Substring patterns for transactions that are almost always solo / individual
# expenses — nobody else owes you a share. When any of these appears in the
# merchant description, "Other people Owe me" is forced to 0 in the export
# (instead of left blank for you to fill in).
#
# Splitwise-matched transactions still use their split amounts — the user's
# explicit match wins over this heuristic.
#
# Intentionally does NOT include "subway" — real NYC subway charges post as
# "MTA*NYCT PAYGO" / "MTA NYCT PAYGO", which the "mta"/"nyct" patterns catch.
# A bare "Subway" line is almost always the sandwich chain.
SOLO_EXPENSE_PATTERNS = (
    "mta",           # MTA tap-to-pay, NYCT PAYGO, LIRR, Metro-North
    "nyct",
    "path tapp",     # PATH (NJ)
    "lirr",
    "metro-north",
    "metro north",
)

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
