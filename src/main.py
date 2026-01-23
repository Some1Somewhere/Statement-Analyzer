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
    extractor = PDFExtractor()
    categorizer = Categorizer()
    formatter = Formatter()

    # Load and categorize
    transactions = extractor.get_all_transactions()

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
    extractor = PDFExtractor()
    categorizer = Categorizer()
    formatter = Formatter()

    # Step 1: Extract
    print("=" * 60)
    print("STEP 1: Extracting transactions from PDFs")
    print("=" * 60)

    if args.input:
        input_path = Path(args.input)
        if input_path.is_dir():
            # Check if it's a card-specific folder or root statements folder
            if input_path.name in CARD_TYPES:
                extractor.process_card_folder(input_path.name, input_path)
            else:
                # Assume it's a custom statements root
                for card_type in CARD_TYPES.keys():
                    card_folder = input_path / card_type
                    if card_folder.exists():
                        extractor.process_card_folder(card_type, card_folder)
        else:
            print(f"Error: Input path is not a directory: {input_path}")
            return 1
    else:
        extractor.process_all_statements()

    # Step 2: Load and categorize
    print("\n" + "=" * 60)
    print("STEP 2: Categorizing transactions")
    print("=" * 60)

    transactions = extractor.get_all_transactions()

    if not transactions:
        print("No transactions extracted. Check that PDFs are in the statements folder.")
        return 1

    categorized = categorizer.categorize_transactions(transactions)
    print(f"Categorized {len(categorized)} transactions")

    # Step 3: Export
    print("\n" + "=" * 60)
    print("STEP 3: Exporting to CSV")
    print("=" * 60)

    output_path = Path(args.output) if args.output else OUTPUT_DIR / "expenses.csv"
    formatter.export_to_csv(categorized, output_path)

    # Print summary
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
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())


