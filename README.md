# Statement Analyzer

A CLI tool to extract expenses from credit card PDF statements using Gemini AI, auto-categorize them, merge Splitwise shared expense data, and output to a standardized CSV format.

## Setup

1. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up API keys:**
   - Get your Gemini API key from https://aistudio.google.com/app/apikey
   - Get your Splitwise API key from https://secure.splitwise.com/apps (register an app, use the API key)
   - Create a `.env` file with:
     ```
     GEMINI_API_KEY=your_api_key_here
     SPLITWISE_API_KEY=your_api_key_here
     ```

4. **Configure your cards:**
   - Copy `data/cards.example.json` to `data/cards.json`
   - Edit to add your card types:
     ```json
     {
       "chase_sapphire": "Chase Sapphire",
       "amex_gold": "Amex Gold",
       "savings": "Savings Account"
     }
     ```
   - Create matching folders in `statements/` for each card key

5. **Configure categories:**
   - Copy `data/categories.example.json` to `data/categories.json`
   - Add keywords for your merchants

## Usage

### Full Pipeline (Extract + Categorize + Export)
```bash
python -m src.main run
```

### Individual Commands

**Extract from PDFs** (uses Gemini API):
```bash
# Extract from all card folders
python -m src.main extract

# Extract from a specific card
python -m src.main extract --card chase_sapphire

# Only process files modified in the last 30 days (for incremental updates)
python -m src.main extract --days 30

# Clear old data and re-extract everything fresh
python -m src.main extract --clear
```

**Export to CSV** (uses cached intermediate data):
```bash
# Re-categorize and export (no API calls)
python -m src.main export --summary

# Export to Excel
python -m src.main export --format xlsx
```

**Splitwise Integration:**
```bash
# Fetch and cache Splitwise expenses (USD only)
python -m src.main fetch-splitwise

# Fetch only recent expenses
python -m src.main fetch-splitwise --days 30

# Interactively match card transactions to Splitwise shared expenses
python -m src.main match-splitwise
```

**Other Commands:**
```bash
# List available card types and PDF counts
python -m src.main list-cards

# Add a keyword to a category
python -m src.main add-keyword Restaurant "new restaurant name"
```

## Monthly Workflow

When you have new statements to process:

1. **Add new PDF statements** to the appropriate folder in `statements/`

2. **Extract card transactions from PDFs:**
   ```bash
   python -m src.main extract --days 30
   ```
   Or clear old data and re-extract everything fresh:
   ```bash
   python -m src.main extract --clear
   ```

3. **Fetch Splitwise expenses for the same period:**
   ```bash
   python -m src.main fetch-splitwise --days 30
   ```

4. **Match card charges to Splitwise shared expenses:**
   ```bash
   python -m src.main match-splitwise
   ```
   This shows each Splitwise expense you paid for and ranks card transactions by date/amount similarity. You pick which card charge corresponds to each. Matches are saved to `data/splitwise_matches.json` and persist across exports.

5. **Export to CSV:**
   ```bash
   python -m src.main export --summary
   ```

### What `export` does

The export command merges data from multiple sources:
- **Card transactions** from PDF extraction (intermediate cache)
- **"Others paid" Splitwise expenses** — things friends paid where you owe a share. These don't appear on any card, so they're added as new rows with source "Splitwise"
- **Match adjustments** — for card transactions matched to Splitwise, the amounts are split: "Amount I owe" shows your share, "Other people Owe me" shows what others owe

### Reading the output

In the `Other people Owe me` column:
- **Blank** = not yet determined (review manually — is this a shared expense?)
- **0** = auto-set for work expenses (Subway)
- **A dollar amount** = Splitwise-matched, automatically computed from the split

> **Note:** The `export` command combines ALL intermediate JSON files. Use `--clear` when extracting to start fresh and avoid duplicates.

## Folder Structure

```
statements/           # Put your PDF statements here
├── {card_key_1}/     # Folder names match keys in cards.json
├── {card_key_2}/
└── ...

data/
├── cards.json              # Your card configuration (gitignored)
├── cards.example.json
├── categories.json         # Your category keywords (gitignored)
├── categories.example.json
├── splitwise_matches.json  # Card-to-Splitwise match mappings (gitignored)
└── intermediate/           # Cached extraction results (JSON)
    ├── {card}_{file}.json  # Per-statement card transaction cache
    └── splitwise_expenses.json  # Splitwise API response cache

output/
└── expenses.csv      # Final output
```

## Output Format

| Column | Description |
|--------|-------------|
| Date | Transaction date (YYYY-MM-DD) |
| Month | Month name |
| Category | Auto-categorized (Health, Rent, Restaurant, etc.) |
| Item | Transaction description |
| Payment Type | Which card was used (or "Splitwise" for others-paid expenses) |
| Amount Charged | Full transaction amount |
| Other people Owe me | Splitwise-computed split, 0 for work expenses, blank for manual review |
| Amount I owe | Your portion (full amount if unmatched, split amount if Splitwise-matched) |
| Notes | Empty, for manual notes |

## Categories

Default categories:
- Health, Rent, Restaurant, Transport, Groceries
- Work, Entertainment, Household, Gift
- Intoxicants, Vacations, Dates, Misc

Edit `data/categories.json` to add keywords for auto-categorization:

```json
{
  "Restaurant": ["uber eats", "doordash", "chipotle", ...],
  "Groceries": ["trader joe", "whole foods", ...],
  ...
}
```

Then re-export (no need to re-extract):
```bash
python -m src.main export --summary
```

## License

MIT
