#!/usr/bin/env python3
"""
Statement Analyzer - Credit Card Statement Processing Tool

CLI tool to extract, categorize, and format expenses from credit card statements.

Usage:
    python -m src.main extract [--card TYPE] [--input PATH]
    python -m src.main categorize [--use-ai]
    python -m src.main fetch-splitwise [--days N]
    python -m src.main match-splitwise
    python -m src.main manual-match SPLITWISE_ROW EXPENSES_ROW
    python -m src.main export [--output PATH] [--format csv|xlsx]
    python -m src.main run [--input PATH] [--output PATH]
"""

import argparse
import sys
from pathlib import Path

from .config import STATEMENTS_DIR, OUTPUT_DIR, CARD_TYPES, SPLITWISE_DEFAULT_DAYS
from .pdf_extractor import PDFExtractor
from .categorizer import Categorizer
from .formatter import Formatter


def cmd_extract(args):
    """Extract transactions from PDF statements."""
    extractor = PDFExtractor()
    days = args.days if hasattr(args, 'days') else None

    # Clear old intermediate files if requested
    if args.clear:
        extractor.clear_intermediate()

    if args.card:
        # Process specific card type
        if args.card not in CARD_TYPES:
            print(f"Error: Unknown card type '{args.card}'")
            print(f"Available types: {', '.join(CARD_TYPES.keys())}")
            return 1

        input_path = Path(args.input) if args.input else None
        extractor.process_card_folder(args.card, input_path, days=days, force=args.force)
    else:
        # Process all card types
        extractor.process_all_statements(days=days, force=args.force)

    return 0


def cmd_categorize(args):
    """Categorize extracted transactions."""
    extractor = PDFExtractor()
    categorizer = Categorizer(use_gemini_fallback=args.use_ai)

    # Load intermediate results
    transactions = extractor.get_all_transactions()

    if not transactions:
        print("No transactions found. Run 'extract' command first.")
        return 1

    print(f"Categorizing {len(transactions)} transactions...")

    # Categorize
    categorized = categorizer.categorize_transactions(transactions)

    # Show stats
    stats = categorizer.get_category_stats(categorized)
    print("\nCategory breakdown:")
    for cat, data in sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True):
        print(f"  {cat}: {data['count']} items, ${data['total']:,.2f}")

    return 0


def cmd_export(args):
    """Export categorized transactions to CSV/Excel."""
    from .splitwise_client import SplitwiseClient
    from .splitwise_matcher import load_matches, apply_matches, export_unmatched_splitwise

    extractor = PDFExtractor()
    categorizer = Categorizer()
    formatter = Formatter()

    # Load card transactions
    transactions = extractor.get_all_transactions()

    # Merge Splitwise "others_paid" transactions
    cached = SplitwiseClient.load_cached()
    if cached:
        my_user_id = cached.get("user_id")
        others_paid = cached.get("others_paid", [])
        if others_paid:
            sw_transactions = SplitwiseClient.to_transactions(others_paid, my_user_id)
            transactions.extend(sw_transactions)
            print(f"Added {len(sw_transactions)} Splitwise expenses (others paid)")

        # Apply match data to card transactions
        matches = load_matches()
        i_paid_shared = cached.get("i_paid_shared", [])
        if matches:
            transactions = apply_matches(
                transactions, matches, i_paid_shared, my_user_id
            )
            applied = sum(1 for t in transactions if t.get("splitwise_matched"))
            print(f"Applied Splitwise splits to {applied} card transaction(s)")

        # Export unmatched Splitwise CSV
        if i_paid_shared:
            export_unmatched_splitwise(i_paid_shared, matches or [], my_user_id)

    if not transactions:
        print("No transactions found. Run 'extract' and/or 'fetch-splitwise' first.")
        return 1

    categorized = categorizer.categorize_transactions(transactions)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        ext = "xlsx" if args.format == "xlsx" else "csv"
        output_path = OUTPUT_DIR / f"expenses.{ext}"

    # Export
    if args.format == "xlsx":
        formatter.export_to_excel(categorized, output_path)
    else:
        formatter.export_to_csv(categorized, output_path)

    # Push to Google Sheet (the manually-curated source of truth), if
    # configured. Additive only — dedup by matching, existing rows untouched.
    # Never fails the export — the CSV is already written.
    from .config import GOOGLE_SHEET_ID
    if GOOGLE_SHEET_ID and args.format != "xlsx":
        try:
            import csv as csv_mod
            from .sheets_client import SheetsClient

            sheets = SheetsClient()
            rows = formatter.format_transactions(categorized).to_dict("records")
            if args.since:
                rows = [r for r in rows if str(r.get("Date", "")) >= args.since]
            if args.dry_run:
                new_rows = sheets.find_new_expenses(rows)
                print(f"Sheet (dry run): would append {len(new_rows)} new row(s)")
                for r in new_rows:
                    print(f"  + {r['Date']} | {r['Item']} | {r['Payment Type']} | {r['Amount Charged']}")
                fills = sheets.find_split_fills(rows)
                fill_rows = sorted({rn for rn, _, _ in fills})
                print(f"Sheet (dry run): would fill splits on {len(fill_rows)} existing row(s)")
                for row_num, col, value in fills:
                    if col == "Other people Owe me":
                        print(f"  ~ row {row_num}: Other people Owe me -> {value}")
            else:
                added = sheets.append_expenses(rows)
                print(f"Sheet: appended {added} new expense row(s)")
                filled = sheets.fill_blank_splits(rows)
                if filled:
                    print(f"Sheet: filled splits on {filled} existing row(s)")

                unmatched_path = OUTPUT_DIR / "unmatched_splitwise.csv"
                if unmatched_path.exists():
                    with open(unmatched_path) as f:
                        unmatched_rows = list(csv_mod.DictReader(f))
                    sheets.replace_unmatched(unmatched_rows)
                    print(f"Sheet: refreshed {len(unmatched_rows)} unmatched Splitwise row(s)")
        except Exception as e:
            print(f"Sheet push failed (CSV still written): {e!r}")

    # Print summary
    if args.summary:
        formatter.print_summary(categorized)

    return 0


def cmd_run(args):
    """Run the full pipeline: extract, fetch Splitwise, optionally match, categorize, export."""
    from .splitwise_client import SplitwiseClient
    from .splitwise_matcher import run_interactive_matching, load_matches, apply_matches

    extractor = PDFExtractor()
    categorizer = Categorizer()
    formatter = Formatter()

    # Step 1: Extract from PDFs
    print("=" * 60)
    print("STEP 1: Extracting transactions from PDFs")
    print("=" * 60)

    if args.input:
        input_path = Path(args.input)
        if input_path.is_dir():
            if input_path.name in CARD_TYPES:
                extractor.process_card_folder(input_path.name, input_path)
            else:
                for card_type in CARD_TYPES.keys():
                    card_folder = input_path / card_type
                    if card_folder.exists():
                        extractor.process_card_folder(card_type, card_folder)
        else:
            print(f"Error: Input path is not a directory: {input_path}")
            return 1
    else:
        extractor.process_all_statements()

    # Step 2: Fetch Splitwise (optional)
    print("\n" + "=" * 60)
    print("STEP 2: Fetching Splitwise expenses")
    print("=" * 60)

    try:
        sw_client = SplitwiseClient()
        sw_client.fetch_and_cache()
    except ValueError:
        print("Skipping Splitwise (no API key configured)")
    except Exception as e:
        print(f"Splitwise fetch failed: {e}")

    # Step 3: Interactive matching (optional)
    cached = SplitwiseClient.load_cached()
    if cached and cached.get("i_paid_shared"):
        choice = input("\nRun Splitwise matching? (y/n): ").strip().lower()
        if choice == "y":
            print("\n" + "=" * 60)
            print("STEP 3: Matching card transactions to Splitwise")
            print("=" * 60)
            card_transactions = extractor.get_all_transactions()
            run_interactive_matching(
                splitwise_shared=cached["i_paid_shared"],
                card_transactions=card_transactions,
                my_user_id=cached.get("user_id"),
            )

    # Step 4: Load, merge, categorize
    print("\n" + "=" * 60)
    print("STEP 4: Categorizing transactions")
    print("=" * 60)

    transactions = extractor.get_all_transactions()

    # Merge Splitwise "others_paid"
    if cached:
        my_user_id = cached.get("user_id")
        others_paid = cached.get("others_paid", [])
        if others_paid:
            sw_txns = SplitwiseClient.to_transactions(others_paid, my_user_id)
            transactions.extend(sw_txns)

        # Apply matches
        matches = load_matches()
        i_paid_shared = cached.get("i_paid_shared", [])
        if matches:
            transactions = apply_matches(
                transactions, matches, i_paid_shared, my_user_id
            )

    if not transactions:
        print("No transactions found.")
        return 1

    categorized = categorizer.categorize_transactions(transactions)
    print(f"Categorized {len(categorized)} transactions")

    # Step 5: Export
    print("\n" + "=" * 60)
    print("STEP 5: Exporting to CSV")
    print("=" * 60)

    output_path = Path(args.output) if args.output else OUTPUT_DIR / "expenses.csv"
    formatter.export_to_csv(categorized, output_path)
    formatter.print_summary(categorized)

    return 0


def cmd_list_cards(args):
    """List available card types."""
    print("Available card types:")
    for key, name in CARD_TYPES.items():
        folder = STATEMENTS_DIR / key
        status = "✓" if folder.exists() else "✗"
        pdf_count = len(list(folder.glob("*.pdf"))) if folder.exists() else 0
        print(f"  {status} {key}: {name} ({pdf_count} PDFs)")


def cmd_add_keyword(args):
    """Add a keyword to a category."""
    categorizer = Categorizer()

    if categorizer.add_keyword(args.category, args.keyword):
        print(f"Added '{args.keyword}' to category '{args.category}'")
    else:
        print("Failed to add keyword")


def cmd_fetch_splitwise(args):
    """Fetch expenses from Splitwise API."""
    from .splitwise_client import SplitwiseClient
    from .splitwise_matcher import load_matches, save_matches, backfill_match_amounts

    client = SplitwiseClient()

    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    dated_after = cutoff.isoformat()

    cached = client.fetch_and_cache(dated_after=dated_after)

    # Enrich legacy matches with split amounts from the fresh cache, so they
    # keep working even after the cache window moves past them.
    matches = load_matches()
    if matches:
        updated = backfill_match_amounts(
            matches, cached.get("i_paid_shared", []), cached.get("user_id")
        )
        if updated:
            save_matches(matches)
            print(f"Backfilled split amounts into {updated} existing match(es)")
    return 0


def cmd_match_splitwise(args):
    """Interactive matching of card transactions to Splitwise expenses."""
    from .splitwise_client import SplitwiseClient
    from .splitwise_matcher import run_interactive_matching

    # Load Splitwise cached data
    cached = SplitwiseClient.load_cached()
    if cached is None:
        print("No Splitwise data found. Run 'fetch-splitwise' first.")
        return 1

    # Load card transactions
    extractor = PDFExtractor()
    card_transactions = extractor.get_all_transactions()

    if not card_transactions:
        print("No card transactions found. Run 'extract' first.")
        return 1

    run_interactive_matching(
        splitwise_shared=cached.get("i_paid_shared", []),
        card_transactions=card_transactions,
        my_user_id=cached.get("user_id"),
    )
    return 0


def cmd_manual_match(args):
    """Manually match a Splitwise expense to a card transaction by row numbers."""
    import csv as csv_mod
    import json
    from .splitwise_matcher import load_matches, save_matches
    from datetime import datetime as dt

    unmatched_path = OUTPUT_DIR / "unmatched_splitwise.csv"
    expenses_path = OUTPUT_DIR / "expenses.csv"

    if not unmatched_path.exists():
        print(f"Not found: {unmatched_path}")
        print("Run 'export' first to generate the CSVs.")
        return 1
    if not expenses_path.exists():
        print(f"Not found: {expenses_path}")
        print("Run 'export' first to generate the CSVs.")
        return 1

    # Read unmatched CSV rows
    with open(unmatched_path) as f:
        unmatched_rows = list(csv_mod.DictReader(f))

    # Read expenses CSV rows
    with open(expenses_path) as f:
        expenses_rows = list(csv_mod.DictReader(f))

    sw_row_num = args.splitwise_row
    exp_row_num = args.expenses_row

    if sw_row_num < 1 or sw_row_num > len(unmatched_rows):
        print(f"Invalid unmatched row {sw_row_num}. File has {len(unmatched_rows)} rows.")
        return 1
    if exp_row_num < 1 or exp_row_num > len(expenses_rows):
        print(f"Invalid expenses row {exp_row_num}. File has {len(expenses_rows)} rows.")
        return 1

    sw_row = unmatched_rows[sw_row_num - 1]
    exp_row = expenses_rows[exp_row_num - 1]

    sw_id = int(sw_row["Splitwise ID"])
    sw_desc = sw_row["Description"]
    sw_date = sw_row["Date"]
    exp_desc = exp_row["Item"]
    exp_date = exp_row["Date"]
    exp_amount = exp_row["Amount Charged"]

    # Resolve the card transaction id from the row map written during export.
    # This is the exact id export used for that CSV row, so it cannot drift from
    # the displayed order (unlike re-deriving and re-sorting the list here).
    rowmap_path = expenses_path.parent / f"{expenses_path.stem}.rowmap.json"
    if not rowmap_path.exists():
        print(f"Row map not found: {rowmap_path}")
        print("Re-run 'export' to regenerate it, then try again.")
        return 1
    with open(rowmap_path) as f:
        row_ids = json.load(f)

    if len(row_ids) != len(expenses_rows):
        print("Row map is out of sync with expenses.csv. Re-run 'export'.")
        return 1

    card_id = row_ids[exp_row_num - 1]
    if not card_id:
        print(f"Row {exp_row_num} has no matchable card transaction.")
        return 1

    # Confirm with user
    print(f"Splitwise (row {sw_row_num}): {sw_desc} | ${sw_row['You Paid']} | {sw_date}")
    print(f"Card (row {exp_row_num}):      {exp_desc} | ${exp_amount} | {exp_date}")
    confirm = input("Match these? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return 0

    # Save the match, with split amounts stored so it survives cache refetches.
    matches = load_matches()
    record = {
        "splitwise_id": sw_id,
        "card_transaction_id": card_id,
        "matched_at": dt.now().isoformat(),
    }
    try:
        record["owed_share"] = float(sw_row["Your Share"])
        record["others_owe"] = float(sw_row["Others Owe You"])
    except (KeyError, ValueError):
        pass  # legacy CSV without amounts — apply will fall back to the cache
    matches.append(record)
    save_matches(matches)
    print("Matched! Run 'export' to update CSVs.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Statement Analyzer - Process credit card statements"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Extract from PDF statements")
    extract_parser.add_argument(
        "--card", "-c", choices=list(CARD_TYPES.keys()), help="Specific card type"
    )
    extract_parser.add_argument(
        "--input", "-i", help="Input folder path (defaults to statements/)"
    )
    extract_parser.add_argument(
        "--days", "-d", type=int, help="Only process files modified in the last N days"
    )
    extract_parser.add_argument(
        "--clear", action="store_true", help="Clear old intermediate data before extracting"
    )
    extract_parser.add_argument(
        "--force", action="store_true",
        help="Re-extract PDFs that already have intermediate data"
    )

    # Categorize command
    cat_parser = subparsers.add_parser("categorize", help="Categorize transactions")
    cat_parser.add_argument(
        "--use-ai", action="store_true", help="Use Gemini Pro for ambiguous items"
    )

    # Export command
    export_parser = subparsers.add_parser("export", help="Export to CSV/Excel")
    export_parser.add_argument("--output", "-o", help="Output file path")
    export_parser.add_argument(
        "--format", "-f", choices=["csv", "xlsx"], default="csv", help="Output format"
    )
    export_parser.add_argument(
        "--summary", "-s", action="store_true", help="Print summary after export"
    )
    export_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show which rows would be appended to the Google Sheet without writing"
    )
    export_parser.add_argument(
        "--since", metavar="YYYY-MM-DD",
        help="Only consider rows on/after this date for the Sheet push "
             "(CSV always contains everything)"
    )

    # Run command (full pipeline)
    run_parser = subparsers.add_parser("run", help="Run full pipeline")
    run_parser.add_argument("--input", "-i", help="Input statements folder")
    run_parser.add_argument("--output", "-o", help="Output CSV path")

    # List cards command
    subparsers.add_parser("list-cards", help="List available card types")

    # Add keyword command
    kw_parser = subparsers.add_parser("add-keyword", help="Add keyword to category")
    kw_parser.add_argument("category", help="Category name")
    kw_parser.add_argument("keyword", help="Keyword to add")

    # Fetch Splitwise command
    sw_parser = subparsers.add_parser(
        "fetch-splitwise", help="Fetch expenses from Splitwise"
    )
    sw_parser.add_argument(
        "--days", "-d", type=int, default=SPLITWISE_DEFAULT_DAYS,
        help=f"Fetch expenses from the last N days (default: {SPLITWISE_DEFAULT_DAYS})"
    )

    # Match Splitwise command
    subparsers.add_parser(
        "match-splitwise", help="Interactively match card transactions to Splitwise"
    )

    # Manual match command
    mm_parser = subparsers.add_parser(
        "manual-match", help="Manually match a Splitwise expense to a card transaction"
    )
    mm_parser.add_argument(
        "splitwise_row", type=int,
        help="Row number from unmatched_splitwise.csv (1-indexed)"
    )
    mm_parser.add_argument(
        "expenses_row", type=int,
        help="Row number from expenses.csv (1-indexed)"
    )

    args = parser.parse_args()

    if args.command == "extract":
        return cmd_extract(args)
    elif args.command == "categorize":
        return cmd_categorize(args)
    elif args.command == "export":
        return cmd_export(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "list-cards":
        return cmd_list_cards(args)
    elif args.command == "add-keyword":
        return cmd_add_keyword(args)
    elif args.command == "fetch-splitwise":
        return cmd_fetch_splitwise(args)
    elif args.command == "match-splitwise":
        return cmd_match_splitwise(args)
    elif args.command == "manual-match":
        return cmd_manual_match(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())


