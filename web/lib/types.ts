export type Expense = {
  id: string; // Sheet row number — writes re-verify Date+Item before saving
  date: string; // YYYY-MM-DD
  month: string;
  category: string;
  item: string;
  paymentType: string;
  amountCharged: number;
  othersOwe: number | null; // null = blank in Sheet = not yet determined
  amountIOwe: number;
  notes: string;
};

export type ExpensePatch = Partial<
  Pick<Expense, "category" | "amountIOwe" | "othersOwe" | "notes">
>;

// What the client saw in the row it is editing — verified server-side so a
// hand-re-sorted Sheet can never receive an edit on the wrong row. Item and
// charged amount are used because neither is editable from the UI.
export type RowGuard = Pick<Expense, "item" | "amountCharged">;

export type Unmatched = {
  date: string;
  description: string;
  totalCost: number;
  youPaid: number;
  yourShare: number;
  othersOweYou: number;
  splitwiseId: string;
};

export type Candidate = {
  id: string;
  date: string;
  item: string;
  paymentType: string;
  amountCharged: number;
  score: number;
};

export type Match = {
  splitwise_id: number;
  card_transaction_id: string;
  matched_at: string;
};

export const NOT_ON_CARD = "__not_on_card__";

// Mirrors CATEGORIES in src/config.py — update both if you add one.
export const CATEGORIES = [
  "Health", "Rent", "Restaurant", "Transport", "Misc", "Groceries", "Work",
  "Entertainment", "Household", "Gift", "Intoxicants", "Vacations", "Dates",
  "UNKNOWN",
];
