"""PDF extraction module for processing credit card statements."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import STATEMENTS_DIR, INTERMEDIATE_DIR, CARD_TYPES
from .gemini_client import GeminiClient


class PDFExtractor:
    """Extract transactions from PDF statements and store intermediate results."""

    def __init__(self):
        """Initialize the PDF extractor."""
        self.client = GeminiClient()
        # Ensure intermediate directory exists
        INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

    def extract_from_pdf(
        self, pdf_path: Path, card_type: str, save_intermediate: bool = True
    ) -> dict:
        """
        Extract transactions from a single PDF file.

        Args:
            pdf_path: Path to the PDF file
            card_type: Type of card (must be a key in CARD_TYPES)
            save_intermediate: Whether to save results to intermediate JSON

        Returns:
            Dictionary with extraction results
        """
        if card_type not in CARD_TYPES:
            raise ValueError(
                f"Unknown card type: {card_type}. Must be one of {list(CARD_TYPES.keys())}"
            )

        print(f"Extracting from: {pdf_path.name} ({CARD_TYPES[card_type]})")

        # Extract transactions using Gemini
        transactions = self.client.extract_transactions_from_pdf(pdf_path, card_type)

        # Build result structure
        result = {
            "source": card_type,
            "source_display": CARD_TYPES[card_type],
            "file": pdf_path.name,
            "file_path": str(pdf_path),
            "extracted_at": datetime.now().isoformat(),
            "transaction_count": len(transactions),
            "transactions": transactions,
        }

        # Save intermediate result
        if save_intermediate:
            self._save_intermediate(result, pdf_path, card_type)

        print(f"  Found {len(transactions)} transactions")
        return result

    def process_card_folder(
        self, card_type: str, folder_path: Optional[Path] = None, days: Optional[int] = None
    ) -> list[dict]:
        """
        Process all PDFs in a card type's folder.

        Args:
            card_type: Type of card to process
            folder_path: Optional custom folder path (defaults to statements/{card_type})
            days: Only process files modified in the last N days (None = all files)

        Returns:
            List of extraction results
        """
        if folder_path is None:
            folder_path = STATEMENTS_DIR / card_type

        if not folder_path.exists():
            print(f"Folder not found: {folder_path}")
            return []

        pdf_files = list(folder_path.glob("*.pdf")) + list(folder_path.glob("*.PDF"))

        # Filter by modification date if days is specified
        if days is not None:
            cutoff_time = time.time() - (days * 24 * 60 * 60)
            original_count = len(pdf_files)
            pdf_files = [f for f in pdf_files if f.stat().st_mtime >= cutoff_time]
            if original_count > len(pdf_files):
                print(f"  Filtered to {len(pdf_files)}/{original_count} files modified in last {days} days")

        if not pdf_files:
            print(f"No PDF files found in: {folder_path}")
            return []

        print(f"\nProcessing {len(pdf_files)} PDF(s) from {CARD_TYPES.get(card_type, card_type)}...")

        results = []
        for pdf_path in sorted(pdf_files):
            try:
                result = self.extract_from_pdf(pdf_path, card_type)
                results.append(result)
            except Exception as e:
                print(f"  Error processing {pdf_path.name}: {e}")

        return results

    def process_all_statements(self, days: Optional[int] = None) -> list[dict]:
        """
        Process all PDF statements from all card folders.

        Args:
            days: Only process files modified in the last N days (None = all files)

        Returns:
            List of all extraction results
        """
        all_results = []

        if days is not None:
            print(f"Processing files modified in the last {days} days...")

        for card_type in CARD_TYPES.keys():
            results = self.process_card_folder(card_type, days=days)
            all_results.extend(results)

        print(f"\nTotal: Processed {len(all_results)} statement(s)")
        total_transactions = sum(r["transaction_count"] for r in all_results)
        print(f"Total transactions extracted: {total_transactions}")

        return all_results

    def _save_intermediate(self, result: dict, pdf_path: Path, card_type: str) -> Path:
        """Save extraction result to intermediate JSON file."""
        # Create filename based on source and original filename
        stem = pdf_path.stem
        output_filename = f"{card_type}_{stem}.json"
        output_path = INTERMEDIATE_DIR / output_filename

        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)

        print(f"  Saved to: {output_path.name}")
        return output_path

    def clear_intermediate(self):
        """Clear all intermediate JSON files."""
        json_files = list(INTERMEDIATE_DIR.glob("*.json"))
        if json_files:
            print(f"Clearing {len(json_files)} intermediate file(s)...")
            for f in json_files:
                f.unlink()
            print("  Done.")
        else:
            print("No intermediate files to clear.")

    def load_intermediate_results(self) -> list[dict]:
        """
        Load all intermediate JSON results.

        Returns:
            List of all extraction results from intermediate files
        """
        results = []
        json_files = list(INTERMEDIATE_DIR.glob("*.json"))

        for json_path in sorted(json_files):
            try:
                with open(json_path) as f:
                    result = json.load(f)
                    results.append(result)
            except Exception as e:
                print(f"Error loading {json_path.name}: {e}")

        return results

    def get_all_transactions(self) -> list[dict]:
        """
        Get all transactions from intermediate results with source info.

        Returns:
            Flat list of all transactions with source metadata
        """
        results = self.load_intermediate_results()
        all_transactions = []

        for result in results:
            source = result.get("source", "unknown")
            source_display = result.get("source_display", source)

            for txn in result.get("transactions", []):
                # Add source info to each transaction
                txn_with_source = {
                    **txn,
                    "source": source,
                    "source_display": source_display,
                    "statement_file": result.get("file", ""),
                }
                all_transactions.append(txn_with_source)

        return all_transactions

