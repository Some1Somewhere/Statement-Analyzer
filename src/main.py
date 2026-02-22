#!/usr/bin/env python3
"""
Statement Analyzer - Credit Card Statement Processing Tool

CLI tool to extract, categorize, and format expenses from credit card statements.

Usage:
    python -m src.main extract [--card TYPE] [--input PATH]
    python -m src.main categorize [--use-ai]
    python -m src.main export [--output PATH] [--format csv|xlsx]
    python -m src.main run [--input PATH] [--output PATH]
"""

import argparse
import sys
from pathlib import Path

from .config import STATEMENTS_DIR, OUTPUT_DIR, CARD_TYPES
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
        extractor.process_card_folder(args.card, input_path, days=days)
    else:
        # Process all card types
        extractor.process_all_statements(days=days)

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
        if matches and i_paid_shared:
            transactions = apply_matches(
                transactions, matches, i_paid_shared, my_user_id
            )
            real_matches = [m for m in matches if m["card_transaction_id"] != "__not_on_card__"]
            print(f"Applied {len(real_matches)} Splitwise match(es)")

        # Export unmatched Splitwise CSV
        if i_paid_shared:
            export_unmatched_splitwise(i_paid_shared, matches or [], my_user_id)

    if not transactions:
        print("No transactions found. Run 'extract' command first.")
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

    # Print summary
    if args.summary:
        formatter.print_summary(categorized)

    return 0


def cmd_run(args):
    """Run the full pipeline: extract, categorize, export."""
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
        if matches and i_paid_shared:
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
        print(f"Failed to add keyword")


def cmd_fetch_splitwise(args):
    """Fetch expenses from Splitwise API."""
    from .splitwise_client import SplitwiseClient

    client = SplitwiseClient()

    dated_after = None
    if args.days:
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=args.days)
        dated_after = cutoff.isoformat() + "Z"

    client.fetch_and_cache(dated_after=dated_after)
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
    from .splitwise_client import SplitwiseClient
    from .splitwise_matcher import (
        generate_transaction_id, load_matches, save_matches,
    )
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

    # Find the card transaction that matches this expenses.csv row
    # Load card transactions in the same order as export
    extractor = PDFExtractor()
    card_transactions = extractor.get_all_transactions()
    # Filter credits, sort by date — same as formatter
    card_transactions = [t for t in card_transactions if not t.get("is_credit")]
    card_transactions.sort(key=lambda t: t.get("date", ""))

    # Also include Splitwise "others_paid" in same order as export
    cached = SplitwiseClient.load_cached()
    if cached:
        others_paid = cached.get("others_paid", [])
        if others_paid:
            sw_txns = SplitwiseClient.to_transactions(others_paid, cached.get("user_id"))
            sw_txns = [t for t in sw_txns if not t.get("is_credit")]
            card_transactions.extend(sw_txns)
            card_transactions.sort(key=lambda t: t.get("date", ""))

    if exp_row_num > len(card_transactions):
        print(f"Row {exp_row_num} exceeds available transactions ({len(card_transactions)}).")
        return 1

    matched_txn = card_transactions[exp_row_num - 1]
    card_id = generate_transaction_id(matched_txn)

    # Confirm with user
    print(f"Splitwise (row {sw_row_num}): {sw_desc} | ${sw_row['You Paid']} | {sw_date}")
    print(f"Card (row {exp_row_num}):      {exp_desc} | ${exp_amount} | {exp_date}")
    confirm = input("Match these? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return 0

    # Save the match
    matches = load_matches()
    matches.append({
        "splitwise_id": sw_id,
        "card_transaction_id": card_id,
        "matched_at": dt.now().isoformat(),
    })
    save_matches(matches)
    print(f"Matched! Run 'export' to update CSVs.")
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
        "--days", "-d", type=int, help="Only fetch expenses from the last N days"
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


