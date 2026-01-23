"""Gemini API client for PDF analysis and transaction extraction."""

import json
import google.generativeai as genai
from pathlib import Path
from typing import Optional

from .config import GEMINI_API_KEY, GEMINI_FLASH_MODEL, GEMINI_PRO_MODEL, CATEGORIES


class GeminiClient:
    """Client for interacting with Gemini API for PDF analysis."""

    def __init__(self):
        """Initialize the Gemini client with API key."""
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY not found. Please set it in your .env file."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        self.flash_model = genai.GenerativeModel(GEMINI_FLASH_MODEL)
        self.pro_model = genai.GenerativeModel(GEMINI_PRO_MODEL)

    def extract_transactions_from_pdf(
        self, pdf_path: Path, card_type: str
    ) -> list[dict]:
        """
        Extract transactions from a PDF statement using Gemini Flash.

        Args:
            pdf_path: Path to the PDF file
            card_type: Type of card (e.g., 'chase_sapphire', 'amex_bcp')

        Returns:
            List of transaction dictionaries with date, description, amount
        """
        # Upload the PDF file
        uploaded_file = genai.upload_file(pdf_path, mime_type="application/pdf")

        prompt = self._build_extraction_prompt(card_type)

        try:
            response = self.flash_model.generate_content(
                [uploaded_file, prompt],
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1,  # Low temperature for consistent extraction
                ),
            )

            # Parse the JSON response
            transactions = self._parse_response(response.text)
            return transactions

        except Exception as e:
            print(f"Error extracting from {pdf_path}: {e}")
            return []
        finally:
            # Clean up uploaded file
            try:
                uploaded_file.delete()
            except:
                pass

    def _build_extraction_prompt(self, card_type: str) -> str:
        """Build the extraction prompt for Gemini."""
        return f"""Analyze this {card_type} credit card/bank statement PDF and extract ALL transactions.

For each transaction, extract:
1. date: The transaction date in YYYY-MM-DD format
2. description: The merchant name or transaction description (clean it up, remove extra codes)
3. amount: The transaction amount as a positive number (for charges/debits)
4. is_credit: Boolean - true if this is a payment/credit/refund, false if it's a charge

IMPORTANT RULES:
- Extract EVERY transaction listed in the statement
- For dates, convert to YYYY-MM-DD format
- For amounts, always use positive numbers
- Clean up merchant names (remove transaction IDs, extra numbers, location codes)
- Mark payments to the card, refunds, and credits as is_credit: true
- Mark regular purchases and charges as is_credit: false
- If a transaction date spans multiple days (e.g., "10/15 - 10/17"), use the first date

Return a JSON array of transactions in this exact format:
[
  {{
    "date": "2024-10-15",
    "description": "UBER EATS",
    "amount": 25.50,
    "is_credit": false
  }},
  {{
    "date": "2024-10-16",
    "description": "Payment Thank You",
    "amount": 500.00,
    "is_credit": true
  }}
]

Only return the JSON array, no other text."""

    def _parse_response(self, response_text: str) -> list[dict]:
        """Parse the JSON response from Gemini."""
        try:
            # Try to parse directly
            transactions = json.loads(response_text)
            if isinstance(transactions, list):
                return transactions
            return []
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            try:
                # Find JSON array in response
                start = response_text.find("[")
                end = response_text.rfind("]") + 1
                if start != -1 and end > start:
                    json_str = response_text[start:end]
                    return json.loads(json_str)
            except:
                pass
            return []

    def categorize_transaction(
        self, description: str, amount: float, existing_category: Optional[str] = None
    ) -> str:
        """
        Use Gemini Pro to categorize an ambiguous transaction.

        Args:
            description: Transaction description
            amount: Transaction amount
            existing_category: Currently assigned category (if any)

        Returns:
            Suggested category from the predefined list
        """
        categories_list = ", ".join(CATEGORIES)

        prompt = f"""Categorize this transaction into ONE of these categories:
{categories_list}

Transaction: {description}
Amount: ${amount:.2f}
{f"Current category: {existing_category}" if existing_category else ""}

Rules:
- Choose the MOST specific category that fits
- If it's a restaurant or food delivery, use "Restaurant"
- If it's grocery store, use "Groceries" 
- If it could fit multiple categories, choose the primary purpose
- Only return the category name, nothing else

Category:"""

        try:
            response = self.pro_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=50,
                ),
            )
            category = response.text.strip()

            # Validate it's a known category
            if category in CATEGORIES:
                return category
            
            # Try to match partial
            for cat in CATEGORIES:
                if cat.lower() in category.lower():
                    return cat

            return "Misc"

        except Exception as e:
            print(f"Error categorizing '{description}': {e}")
            return "Misc"

