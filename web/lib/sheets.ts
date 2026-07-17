// Server-only Google Sheets access. The Sheet is the manually-curated source
// of truth: the SHEET_TAB tab (default "Main") holds reconciled expense rows
// (no id column — the CLI dedups by matching), and "Unmatched Splitwise" is
// replaced on each export.
//
// Rows are addressed by sheet row number. Row numbers only shift if the user
// re-sorts the Sheet by hand, so every write verifies Date+Item first and
// refuses to touch a row that moved.
import fs from "node:fs";
import path from "node:path";
import { JWT } from "google-auth-library";
import {
  GoogleSpreadsheet,
  GoogleSpreadsheetRow,
  GoogleSpreadsheetWorksheet,
} from "google-spreadsheet";
import type { Expense, ExpensePatch, RowGuard, Unmatched } from "./types";
import { NOT_ON_CARD } from "./types";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const SERVICE_ACCOUNT_FILE =
  process.env.GOOGLE_SERVICE_ACCOUNT_FILE ??
  path.join(PROJECT_ROOT, "data", "service-account.json");

const EXPENSES_TAB = process.env.SHEET_TAB ?? "Main";
const UNMATCHED_TAB = "Unmatched Splitwise";

async function loadDoc(): Promise<GoogleSpreadsheet> {
  const sheetId = process.env.GOOGLE_SHEET_ID;
  if (!sheetId) {
    throw new Error("GOOGLE_SHEET_ID is not set — add it to the root .env");
  }
  if (!fs.existsSync(SERVICE_ACCOUNT_FILE)) {
    throw new Error(`Service account file not found: ${SERVICE_ACCOUNT_FILE}`);
  }
  const creds = JSON.parse(fs.readFileSync(SERVICE_ACCOUNT_FILE, "utf8"));
  const auth = new JWT({
    email: creds.client_email,
    key: creds.private_key,
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });
  const doc = new GoogleSpreadsheet(sheetId, auth);
  await doc.loadInfo();
  return doc;
}

async function getTab(title: string): Promise<GoogleSpreadsheetWorksheet> {
  const doc = await loadDoc();
  const sheet = doc.sheetsByTitle[title];
  if (!sheet) throw new Error(`Tab "${title}" not found in the Sheet`);
  return sheet;
}

const num = (v: unknown): number => {
  const n = parseFloat(String(v ?? "").replace(/[$,]/g, ""));
  return Number.isFinite(n) ? n : 0;
};

const numOrNull = (v: unknown): number | null =>
  String(v ?? "").trim() === "" ? null : num(v);

// The Sheet is hand-edited: dates arrive as "2026-05-07", "5/7/2026",
// "5/7/26", or just "5/7" (no year). Year resolution order: the date itself,
// then the Month column ("April '25"), then carried forward from the previous
// row — the Sheet is appended chronologically.
const MONTH_NUM: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7,
  august: 8, september: 9, october: 10, november: 11, december: 12,
};

type DateParts = { y: number | null; m: number | null; d: number | null };

function parseDateCell(raw: string): DateParts {
  const iso = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (iso) return { y: Number(iso[1]), m: Number(iso[2]), d: Number(iso[3]) };
  const us = raw.match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?$/);
  if (us) {
    const y = us[3] ? Number(us[3].length === 2 ? `20${us[3]}` : us[3]) : null;
    return { y, m: Number(us[1]), d: Number(us[2]) };
  }
  return { y: null, m: null, d: null };
}

function parseMonthCell(raw: string): { m: number | null; y: number | null } {
  const name = raw.trim().toLowerCase().match(/^([a-z]+)/)?.[1] ?? "";
  const yy = raw.match(/'(\d{2})/);
  return { m: MONTH_NUM[name] ?? null, y: yy ? 2000 + Number(yy[1]) : null };
}

const pad = (n: number): string => String(n).padStart(2, "0");

function rowToExpense(row: GoogleSpreadsheetRow, resolvedDate?: string): Expense {
  return {
    id: String(row.rowNumber),
    date: resolvedDate ?? String(row.get("Date") ?? "").trim(),
    month: String(row.get("Month") ?? ""),
    category: String(row.get("Category") ?? ""),
    item: String(row.get("Item") ?? ""),
    paymentType: String(row.get("Payment Type") ?? ""),
    amountCharged: num(row.get("Amount Charged")),
    othersOwe: numOrNull(row.get("Other people Owe me")),
    amountIOwe: num(row.get("Amount I owe")),
    notes: String(row.get("Notes") ?? ""),
  };
}

export async function getExpenses(): Promise<Expense[]> {
  const sheet = await getTab(EXPENSES_TAB);
  const rows = await sheet.getRows();

  let lastYear: number | null = null;
  let lastMonth: number | null = null;

  const expenses: Expense[] = [];
  for (const row of rows) {
    const raw = String(row.get("Date") ?? "").trim();
    const date = parseDateCell(raw);
    const monthCol = parseMonthCell(String(row.get("Month") ?? ""));

    const m = date.m ?? monthCol.m;
    let y: number | null = date.y ?? monthCol.y ?? lastYear;
    // ponytail: year-rollover heuristic for carried-forward years (Dec → Jan
    // with no year anywhere). Assumes chronological order; fix rows in the
    // Sheet if it ever misfires.
    if (date.y === null && monthCol.y === null && y !== null && lastMonth !== null && m !== null && m < lastMonth - 6) {
      y += 1;
    }

    let resolved = raw;
    if (y !== null && m !== null) {
      resolved = `${y}-${pad(m)}-${pad(date.d ?? 1)}`;
      lastYear = y;
      lastMonth = m;
    }

    const expense = rowToExpense(row, resolved);
    if (expense.date !== "" || expense.item !== "") expenses.push(expense);
  }
  return expenses;
}

/** Find a row by number and verify it still holds the transaction the client
 *  saw — a hand re-sort of the Sheet shifts row numbers, and money edits must
 *  never land on the wrong row. */
async function findGuardedRow(
  id: string,
  guard: RowGuard,
): Promise<GoogleSpreadsheetRow> {
  const rowNumber = Number(id);
  const sheet = await getTab(EXPENSES_TAB);
  const rows = await sheet.getRows();
  const row = rows.find((r) => r.rowNumber === rowNumber);
  if (!row) throw new Error(`Expense row not found: ${id}`);
  const current = rowToExpense(row);
  if (current.item !== guard.item || current.amountCharged !== guard.amountCharged) {
    throw new Error(
      "stale row: the Sheet changed since this page loaded — reload and retry",
    );
  }
  return row;
}

export async function patchExpense(
  id: string,
  guard: RowGuard,
  patch: ExpensePatch,
): Promise<Expense> {
  const row = await findGuardedRow(id, guard);
  if (patch.category !== undefined) row.set("Category", patch.category);
  if (patch.amountIOwe !== undefined) row.set("Amount I owe", patch.amountIOwe);
  if (patch.othersOwe !== undefined) {
    row.set("Other people Owe me", patch.othersOwe === null ? "" : patch.othersOwe);
  }
  if (patch.notes !== undefined) row.set("Notes", patch.notes);
  await row.save();
  return rowToExpense(row);
}

export async function getUnmatched(): Promise<Unmatched[]> {
  const sheet = await getTab(UNMATCHED_TAB);
  const rows = await sheet.getRows();
  return rows
    .map((row) => {
      const raw = String(row.get("Date") ?? "").trim();
      const p = parseDateCell(raw);
      return {
        date: p.y !== null && p.m !== null ? `${p.y}-${pad(p.m)}-${pad(p.d ?? 1)}` : raw,
      description: String(row.get("Description") ?? ""),
      totalCost: num(row.get("Total Cost")),
      youPaid: num(row.get("You Paid")),
      yourShare: num(row.get("Your Share")),
      othersOweYou: num(row.get("Others Owe You")),
        splitwiseId: String(row.get("Splitwise ID") ?? ""),
      };
    })
    .filter((u) => u.splitwiseId !== "");
}

/**
 * Apply a confirmed match directly to the Sheet: split the card row's
 * amounts and remove the Splitwise expense from the unmatched tab, so the
 * UI reflects the match immediately without re-running the CLI export.
 */
export async function applyMatchToSheet(
  cardId: string,
  cardGuard: RowGuard | null,
  splitwiseId: string,
): Promise<void> {
  const unmatchedSheet = await getTab(UNMATCHED_TAB);
  const unmatchedRows = await unmatchedSheet.getRows();
  const swRow = unmatchedRows.find(
    (r) => String(r.get("Splitwise ID")) === splitwiseId,
  );
  if (!swRow) throw new Error(`Unmatched Splitwise row not found: ${splitwiseId}`);

  if (cardId !== NOT_ON_CARD) {
    if (!cardGuard) throw new Error("cardGuard is required for a card match");
    const expenseRow = await findGuardedRow(cardId, cardGuard);
    expenseRow.set("Amount I owe", num(swRow.get("Your Share")));
    expenseRow.set("Other people Owe me", num(swRow.get("Others Owe You")));
    await expenseRow.save();
  }
  await swRow.delete();
}
