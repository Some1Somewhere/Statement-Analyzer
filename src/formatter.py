"""Output formatter for generating the required CSV format."""

import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import OUTPUT_DIR, OUTPUT_COLUMNS, CARD_TYPES


class Formatter:
    """Format transactions into the required CSV output format."""

    def __init__(self):
        """Initialize the formatter."""
        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def format_transactions(self, transactions: list[dict]) -> pd.DataFrame:
        """
        Format transactions into the required output structure.

        Args:
            transactions: List of categorized transactions with source info

        Returns:
            DataFrame with the required columns
        """
        formatted_rows = []

        for txn in transactions:
            # Skip credits/payments/refunds (they're not expenses)
            if txn.get("is_credit", False):
                continue

            row = self._format_single_transaction(txn)
            formatted_rows.append(row)

        # Create DataFrame with required columns
        df = pd.DataFrame(formatted_rows, columns=OUTPUT_COLUMNS)

        # Sort by date
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("Date", ascending=True)

        # Format date back to string
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        return df

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

        # Get amount
        amount = txn.get("amount", 0)

        description = txn.get("description", "").lower()
        
        # Work expenses (Subway) - reimbursed, so "Other people Owe me" = 0
        # For other transactions, leave empty for manual entry
        is_work_expense = "subway" in description
        other_people_owe = 0 if is_work_expense else ""

        return {
            "Date": date_str,
            "Month": month,
            "Category": txn.get("category", "Misc"),
            "Item": txn.get("description", ""),
            "Payment Type": payment_type,
            "Amount Charged": amount,
            "Other people Owe me": other_people_owe,
            "Amount I owe": amount,
            "Notes": "",  # Empty by default
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

        # Format transactions
        df = self.format_transactions(transactions)

        # Export to CSV
        df.to_csv(output_path, index=False)

        print(f"Exported {len(df)} expenses to: {output_path}")
        return output_path

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

