# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python CLI tool that extracts transactions from credit card/bank PDF statements using Google Gemini AI, auto-categorizes them via keyword matching, merges Splitwise shared expense data, and exports to CSV/Excel for personal expense tracking.

## Workflow

The typical monthly workflow for processing new statements:

```bash
# 1. Place new PDF statements into statements/{card_type}/ folders

# 2. Extract card transactions from PDFs (cached, won't re-process existing)
python -m src.main extract --days 30

# 3. Fetch Splitwise expenses for the same period
python -m src.main fetch-splitwise --days 30

# 4. Interactively match card charges to Splitwise shared expenses
#    (e.g., "$80 Whole Foods on Amex" = "Whole Foods groceries split on Splitwise")
python -m src.main match-splitwise

# 5. Export — merges card + Splitwise data, categorizes, writes CSV
python -m src.main export --summary
```

What `export` does behind the scenes:
- Loads card transactions from intermediate cache
- Adds "others paid" Splitwise expenses as new rows (things friends paid where you owe a share — these don't appear on any card)
- Applies match data to card transactions (splits "Amount I owe" and "Other people Owe me" based on Splitwise shares)
- Categorizes everything via keyword matching
- Writes to `output/expenses.csv`

After export, review `Other people Owe me` column: blank = not yet determined (you fill in manually), 0 = solo / individual expense (auto-set for public transit — MTA, NYCT, PATH, LIRR, Metro-North — where nobody else owes a share), a dollar amount = Splitwise-matched split.

## Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Card extraction
python -m src.main extract              # Extract from all card folders
python -m src.main extract --card chase_sapphire --days 30
python -m src.main extract --clear      # Clear cached data, re-extract

# Splitwise integration
python -m src.main fetch-splitwise          # Fetch & cache Splitwise expenses
python -m src.main fetch-splitwise --days 30
python -m src.main match-splitwise          # Interactive card-to-Splitwise matching

# Export and utilities
python -m src.main export --summary     # Export CSV with category breakdown
python -m src.main export --format xlsx
python -m src.main run                  # Full pipeline: extract + fetch + match + export
python -m src.main list-cards
python -m src.main add-keyword Restaurant "merchant name"

# Tests
python -m pytest tests/ -v
```

## Architecture

### Data Pipeline

```
PDF files in statements/{card_type}/
  → [extract] Gemini Flash API → data/intermediate/{card}_{file}.json (cached)

Splitwise API
  → [fetch-splitwise] → data/intermediate/splitwise_expenses.json (cached)
  → [match-splitwise] → data/splitwise_matches.json (persistent match mappings)

Both sources merge at export:
  → [export] categorize + merge card txns + Splitwise "others paid" + apply matches
  → pandas DataFrame → output/expenses.csv
```

Extraction results are cached as intermediate JSON files. The `export` command re-categorizes from cached data without API calls, so updating `categories.json` keywords takes effect on the next export without re-extracting. Splitwise matches persist across exports in `data/splitwise_matches.json`.

### Module Responsibilities

- **`src/main.py`** — CLI entry point with argparse subcommands. Each `cmd_*` function wires together the other modules.
- **`src/config.py`** — Loads `.env`, `cards.json`, defines `CATEGORIES` list and `OUTPUT_COLUMNS`. All path constants (`STATEMENTS_DIR`, `INTERMEDIATE_DIR`, `OUTPUT_DIR`) are derived from `BASE_DIR` (project root).
- **`src/gemini_client.py`** — Wraps `google-generativeai`. `extract_transactions_from_pdf()` uploads PDF and prompts Gemini Flash for structured JSON. `categorize_transaction()` uses Gemini Pro for ambiguous items.
- **`src/pdf_extractor.py`** — Orchestrates PDF processing. Iterates card folders, calls GeminiClient, saves/loads intermediate JSON. `get_all_transactions()` flattens all cached results into a single list with source metadata attached.
- **`src/categorizer.py`** — Keyword-first categorization from `categories.json`. Scores by longest keyword match. Lazy-loads GeminiClient only when `--use-ai` is set. Also handles `add_keyword` persistence.
- **`src/formatter.py`** — Converts categorized transactions to the output DataFrame. Filters out credits (`is_credit: true`), extracts month names, sorts by date. Solo-expense rule: descriptions matching `config.SOLO_EXPENSE_PATTERNS` (NYC subway / MTA / NYCT / PATH / LIRR / Metro-North) set `Other people Owe me` to 0, since transit is an individual expense nobody else owes a share of. Splitwise-matched transactions get split amounts in "Amount I owe" and "Other people Owe me", and that explicit match wins over the solo-expense heuristic.
- **`src/splitwise_client.py`** — REST wrapper for Splitwise API using `requests`. Fetches expenses, classifies them (others_paid / i_paid_shared / i_paid_solo), filters to USD-only, converts "others_paid" into transaction dicts, caches to `data/intermediate/splitwise_expenses.json`.
- **`src/splitwise_matcher.py`** — Generates deterministic transaction IDs, ranks card transactions as candidates for Splitwise expenses (by date proximity + amount similarity), runs interactive CLI matching, persists matches to `data/splitwise_matches.json`, and applies match data to adjust "Amount I owe" / "Other people Owe me" on card transactions.

### Key Design Decisions

- **Intermediate caching** avoids repeated Gemini API calls. `extract --clear` wipes the cache; `extract --days N` filters by file modification time for incremental processing.
- **Keyword matching scores by length** — longer keyword matches take priority over shorter ones to handle substring overlaps.
- **Credits are excluded from export** — transactions with `is_credit: true` (payments, refunds) are silently skipped in `formatter.py`.

## Configuration Files

- `.env` — Must contain `GEMINI_API_KEY` and `SPLITWISE_API_KEY`
- `data/cards.json` — Maps card folder names to display names (copy from `cards.example.json`)
- `data/categories.json` — Maps category names to keyword arrays (copy from `categories.example.json`)
- `data/splitwise_matches.json` — Persistent card-to-Splitwise match mappings (auto-generated by `match-splitwise`)

All config files plus `statements/`, `output/`, and `data/intermediate/` are gitignored.
