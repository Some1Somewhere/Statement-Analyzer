# Statement Analyzer

A CLI tool to extract expenses from credit card PDF statements using Gemini AI, auto-categorize them, and output to a standardized CSV format.

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

3. **Set up API key:**
   - Get your Gemini API key from https://aistudio.google.com/app/apikey
   - Create a `.env` file with:
     ```
     GEMINI_API_KEY=your_api_key_here
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

2. **Clear old data and extract fresh** (recommended to avoid duplicates):
   ```bash
   python -m src.main extract --clear
   ```
   
   Or if you want to keep old data and only extract new files:
   ```bash
   python -m src.main extract --days 30
   ```

3. **Export to CSV**:
   ```bash
   python -m src.main export --summary
   ```

> **Note:** The `export` command combines ALL intermediate JSON files. Use `--clear` when extracting to start fresh and avoid duplicates.

## Folder Structure

```
statements/           # Put your PDF statements here
├── {card_key_1}/     # Folder names match keys in cards.json
├── {card_key_2}/
└── ...

data/
├── cards.json        # Your card configuration (gitignored)
├── cards.example.json
├── categories.json   # Your category keywords (gitignored)
├── categories.example.json
└── intermediate/     # Cached extraction results (JSON)

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
| Payment Type | Which card was used |
| Amount Charged | Transaction amount |
| Other people Owe me | For shared expenses (fill in manually) |
| Amount I owe | Your portion |
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
