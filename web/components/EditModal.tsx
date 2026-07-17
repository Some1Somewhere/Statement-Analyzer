"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { CATEGORIES, type Expense, type ExpensePatch } from "@/lib/types";
import { fmtDate, fmtUSD } from "@/lib/format";

interface EditModalProps {
  expense: Expense;
  onClose: () => void;
  onSaved: (updated: Expense) => void;
}

export default function EditModal({ expense, onClose, onSaved }: EditModalProps) {
  const [category, setCategory] = useState(expense.category);
  const [amountIOwe, setAmountIOwe] = useState(String(expense.amountIOwe));
  const [othersOwe, setOthersOwe] = useState(
    expense.othersOwe === null ? "" : String(expense.othersOwe),
  );
  const [notes, setNotes] = useState(expense.notes);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const owe = parseFloat(amountIOwe);
    if (!Number.isFinite(owe) || owe < 0) {
      setError("Amount I owe must be a non-negative number");
      return;
    }
    const othersRaw = othersOwe.trim();
    const others = othersRaw === "" ? null : parseFloat(othersRaw);
    if (others !== null && (!Number.isFinite(others) || others < 0)) {
      setError("Other people owe me must be a non-negative number (or blank)");
      return;
    }

    const patch: ExpensePatch = {
      category,
      amountIOwe: owe,
      othersOwe: others,
      notes,
    };
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/expenses", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: expense.id,
          guard: { item: expense.item, amountCharged: expense.amountCharged },
          patch,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      onSaved(data.expense);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Edit ${expense.item}`}
        className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold leading-snug">{expense.item}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1 text-muted hover:bg-background hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>
        <p className="mb-5 text-sm text-muted">
          {fmtDate(expense.date)} · {expense.paymentType} · charged{" "}
          <span className="tnum">{fmtUSD(expense.amountCharged)}</span>
        </p>

        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Category
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="rounded-lg border border-border bg-surface px-3 py-2 text-sm font-normal focus:border-accent focus:outline-none"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Amount I owe
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                value={amountIOwe}
                onChange={(e) => setAmountIOwe(e.target.value)}
                className="tnum rounded-lg border border-border bg-surface px-3 py-2 text-sm font-normal focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Others owe me
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                placeholder="blank = TBD"
                value={othersOwe}
                onChange={(e) => setOthersOwe(e.target.value)}
                className="tnum rounded-lg border border-border bg-surface px-3 py-2 text-sm font-normal focus:border-accent focus:outline-none"
              />
            </label>
          </div>
          <p className="-mt-2 text-xs text-muted">
            Leave “Others owe me” blank if undetermined; 0 means it was a solo expense.
          </p>

          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Notes
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="rounded-lg border border-border bg-surface px-3 py-2 text-sm font-normal focus:border-accent focus:outline-none"
            />
          </label>
        </div>

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-muted hover:bg-background hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-deep disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
