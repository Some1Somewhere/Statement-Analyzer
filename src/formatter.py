"""Output formatter for generating the required CSV format."""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import (
    CARD_TYPES,
    OUTPUT_COLUMNS,
    OUTPUT_DIR,
    SOLO_EXPENSE_PATTERNS,
)
from .splitwise_matcher import generate_transaction_id


class Formatter:
    """Format transactions into the required CSV output format."""

    def __init__(self):
        """Initialize the formatter."""
        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def _build_frame(self, transactions: list[dict]) -> pd.DataFrame:
        """
        Build the sorted output frame, carrying a hidden ``_card_id`` column.

        ``_card_id`` lets callers map each final CSV row back to the
        transaction that produced it (see ``format_with_row_ids``). A stable
        sort keeps same-date rows in their input order so that mapping is
        reproducible across runs.
        """
        formatted_rows = []
        card_ids = []

        for txn in transactions:
            # Skip credits/payments/refunds (they're not expenses)
            if txn.get("is_credit", False):
                continue

            formatted_rows.append(self._format_single_transaction(txn))
            card_ids.append(generate_transaction_id(txn))

        # Create DataFrame with required columns, plus the id sidecar column.
        df = pd.DataFrame(formatted_rows, columns=OUTPUT_COLUMNS)
        df["_card_id"] = card_ids

        # Sort by date (stable, so equal dates keep input order)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("Date", ascending=True, kind="stable")

        # Format date back to string
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        return df

    def format_transactions(self, transactions: list[dict]) -> pd.DataFrame:
        """
        Format transactions into the required output structure.

        Args:
            transactions: List of categorized transactions with source info

        Returns:
            DataFrame with the required columns
        """
        return self._build_frame(transactions).drop(columns=["_card_id"])

    def format_with_row_ids(
        self, transactions: list[dict]
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Format transactions and return the per-row card-transaction ids.

        Returns:
            (DataFrame with the required columns, list of card_transaction_id
            strings in the same order as the DataFrame rows).
        """
        df = self._build_frame(transactions)
        row_ids = df["_card_id"].tolist()
        return df.drop(columns=["_card_id"]), row_ids

    def _format_single_transaction(self, txn: dict) -> dict:
        """
        Format a single transaction into the output row format.

        Args:
            txn: Transaction dictionary

        Returns:
            Dictionary matching OUTPUT_COLUMNS
        """
        # Parse date and extract month
        date_str = txn.get("date", "")
        month = self._extract_month(date_str)

        # Get payment type from source
        source = txn.get("source", "unknown")
        payment_type = CARD_TYPES.get(source, source)
        # Splitwise transactions won't be in CARD_TYPES, use source_display
        if source == "splitwise":
            payment_type = txn.get("source_display", "Splitwise")

        # Get amount
        amount = txn.get("amount", 0)

        # Determine "Amount I owe" and "Other people Owe me"
        if txn.get("splitwise_matched"):
            # Matched to Splitwise: use the split amounts (user's explicit
            # match wins over the solo-expense heuristic).
            amount_i_owe = txn.get("splitwise_owed", amount)
            other_people_owe = txn.get("splitwise_others_owe", 0)
        else:
            description = txn.get("description", "").lower()
            is_solo_expense = any(p in description for p in SOLO_EXPENSE_PATTERNS)
            other_people_owe = 0 if is_solo_expense else ""
            amount_i_owe = amount

        return {
            "Date": date_str,
            "Month": month,
            "Category": txn.get("category", "Misc"),
            "Item": txn.get("description", ""),
            "Payment Type": payment_type,
            "Amount Charged": amount,
            "Other people Owe me": other_people_owe,
            "Amount I owe": amount_i_owe,
            "Notes": "",
        }

    def _extract_month(self, date_str: str) -> str:
        """
        Extract month name from date string.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Month name (e.g., "January", "February")
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj.strftime("%B")
        except (ValueError, TypeError):
            return ""

    def export_to_csv(
        self,
        transactions: list[dict],
        output_path: Optional[Path] = None,
        filename: str = "expenses.csv",
    ) -> Path:
        """
        Export formatted transactions to CSV.

        Args:
            transactions: List of categorized transactions
            output_path: Custom output path (defaults to output/{filename})
            filename: Output filename

        Returns:
            Path to the exported CSV file
        """
        if output_path is None:
            output_path = OUTPUT_DIR / filename

        # Format transactions, keeping the per-row id mapping
        df, row_ids = self.format_with_row_ids(transactions)

        # Export to CSV
        df.to_csv(output_path, index=False)

        # Persist the row -> card_transaction_id map so manual-match can resolve
        # an expenses.csv row number back to its exact transaction.
        self._write_row_map(output_path, row_ids)

        print(f"Exported {len(df)} expenses to: {output_path}")
        return output_path

    @staticmethod
    def _write_row_map(csv_path: Path, row_ids: list[str]) -> Path:
        """Write the ordered card_transaction_id list beside the exported CSV."""
        map_path = csv_path.parent / f"{csv_path.stem}.rowmap.json"
        with open(map_path, "w") as f:
            json.dump(row_ids, f, indent=2)
        return map_path

    def export_to_excel(
        self,
        transactions: list[dict],
        output_path: Optional[Path] = None,
        filename: str = "expenses.xlsx",
    ) -> Path:
        """
        Export formatted transactions to Excel.

        Args:
            transactions: List of categorized transactions
            output_path: Custom output path
            filename: Output filename

        Returns:
            Path to the exported Excel file
        """
        if output_path is None:
            output_path = OUTPUT_DIR / filename

        # Format transactions
        df = self.format_transactions(transactions)

        # Export to Excel
        df.to_excel(output_path, index=False, sheet_name="Expenses")

        print(f"Exported {len(df)} expenses to: {output_path}")
        return output_path

    def get_summary(self, transactions: list[dict]) -> dict:
        """
        Get a summary of the formatted transactions.

        Args:
            transactions: List of categorized transactions

        Returns:
            Summary dictionary
        """
        df = self.format_transactions(transactions)

        summary = {
            "total_expenses": len(df),
            "total_amount": df["Amount Charged"].sum(),
            "by_category": df.groupby("Category")["Amount Charged"]
            .agg(["count", "sum"])
            .to_dict("index"),
            "by_payment_type": df.groupby("Payment Type")["Amount Charged"]
            .agg(["count", "sum"])
            .to_dict("index"),
            "by_month": df.groupby("Month")["Amount Charged"]
            .agg(["count", "sum"])
            .to_dict("index"),
        }

        return summary

    def print_summary(self, transactions: list[dict]):
        """Print a formatted summary of transactions."""
        summary = self.get_summary(transactions)

        print("\n" + "=" * 60)
        print("EXPENSE SUMMARY")
        print("=" * 60)

        print(f"\nTotal Expenses: {summary['total_expenses']}")
        print(f"Total Amount: ${summary['total_amount']:,.2f}")

        print("\n--- By Category ---")
        for cat, data in sorted(
            summary["by_category"].items(), key=lambda x: x[1]["sum"], reverse=True
        ):
            print(f"  {cat}: {data['count']} txns, ${data['sum']:,.2f}")

        print("\n--- By Payment Type ---")
        for card, data in sorted(
            summary["by_payment_type"].items(), key=lambda x: x[1]["sum"], reverse=True
        ):
            print(f"  {card}: {data['count']} txns, ${data['sum']:,.2f}")

        print("\n--- By Month ---")
        for month, data in summary["by_month"].items():
            print(f"  {month}: {data['count']} txns, ${data['sum']:,.2f}")

        print("=" * 60)

