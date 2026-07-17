"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Pencil, Search } from "lucide-react";
import EditModal from "@/components/EditModal";
import { fmtDate, fmtUSD, MONTH_NAMES } from "@/lib/format";
import type { Expense } from "@/lib/types";

export default function Dashboard() {
  const [expenses, setExpenses] = useState<Expense[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [year, setYear] = useState<string | null>(null);
  const [month, setMonth] = useState<number | null>(null); // 1-12
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [editing, setEditing] = useState<Expense | null>(null);

  useEffect(() => {
    fetch("/api/expenses")
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
        setExpenses(data.expenses);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  const years = useMemo(() => {
    if (!expenses) return [];
    return [...new Set(expenses.map((e) => e.date.slice(0, 4)))]
      .filter(Boolean)
      .sort()
      .reverse();
  }, [expenses]);

  const activeYear = year ?? years[0] ?? null;

  // Year + category scope drives the monthly chart (so a category drill-down
  // shows that category's trend); month narrows the rest.
  const yearScope = useMemo(
    () =>
      (expenses ?? []).filter(
        (e) =>
          (!activeYear || e.date.startsWith(activeYear)) &&
          (!category || e.category === category),
      ),
    [expenses, activeYear, category],
  );

  const monthScope = useMemo(
    () =>
      yearScope.filter((e) => !month || Number(e.date.slice(5, 7)) === month),
    [yearScope, month],
  );

  const ledger = useMemo(() => {
    const q = search.trim().toLowerCase();
    return monthScope
      .filter((e) => !q || e.item.toLowerCase().includes(q) || e.paymentType.toLowerCase().includes(q))
      .filter((e) => !reviewOnly || e.othersOwe === null)
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [monthScope, search, reviewOnly]);

  const stats = useMemo(() => {
    const sum = (fn: (e: Expense) => number) => ledger.reduce((acc, e) => acc + fn(e), 0);
    return {
      mySpend: sum((e) => e.amountIOwe),
      charged: sum((e) => e.amountCharged),
      owedToMe: sum((e) => e.othersOwe ?? 0),
      unassigned: ledger.filter((e) => e.othersOwe === null).length,
    };
  }, [ledger]);

  const monthTotals = useMemo(() => {
    const totals = Array(12).fill(0) as number[];
    for (const e of yearScope) {
      const m = Number(e.date.slice(5, 7));
      if (m >= 1 && m <= 12) totals[m - 1] += e.amountIOwe;
    }
    return totals;
  }, [yearScope]);

  const categoryTotals = useMemo(() => {
    const map = new Map<string, number>();
    // Category list ignores the category filter so you can switch between them.
    const scope = (expenses ?? []).filter(
      (e) =>
        (!activeYear || e.date.startsWith(activeYear)) &&
        (!month || Number(e.date.slice(5, 7)) === month),
    );
    for (const e of scope) map.set(e.category, (map.get(e.category) ?? 0) + e.amountIOwe);
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [expenses, activeYear, month]);

  if (loadError) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-border bg-surface p-6">
        <p className="mb-1 flex items-center gap-2 font-medium text-red-600">
          <AlertCircle size={16} /> Couldn’t load expenses
        </p>
        <p className="text-sm text-muted">{loadError}</p>
      </div>
    );
  }

  if (!expenses) {
    return <p className="text-sm text-muted">Loading expenses from the Sheet…</p>;
  }

  const maxMonth = Math.max(...monthTotals, 1);
  const maxCategory = categoryTotals[0]?.[1] ?? 1;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {category ?? "All spending"}
            {month && activeYear ? ` — ${MONTH_NAMES[month - 1]} ${activeYear}` : activeYear ? ` — ${activeYear}` : ""}
          </h1>
          <p className="text-sm text-muted">
            {ledger.length} transaction{ledger.length === 1 ? "" : "s"}
            {(month || category || reviewOnly) && (
              <button
                onClick={() => { setMonth(null); setCategory(null); setReviewOnly(false); }}
                className="ml-2 text-accent hover:underline"
              >
                clear filters
              </button>
            )}
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
          {years.map((y) => (
            <button
              key={y}
              onClick={() => { setYear(y); setMonth(null); }}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                y === activeYear ? "bg-accent font-medium text-white" : "text-muted hover:text-foreground"
              }`}
            >
              {y}
            </button>
          ))}
        </div>
      </header>

      {/* Stat tiles */}
      <section aria-label="Totals" className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="My spend" value={fmtUSD(stats.mySpend)} emphasis />
        <StatTile label="Charged to cards" value={fmtUSD(stats.charged)} />
        <StatTile label="Others owe me" value={fmtUSD(stats.owedToMe)} />
        <button
          onClick={() => setReviewOnly((v) => !v)}
          className={`rounded-xl border p-4 text-left transition-colors ${
            reviewOnly ? "border-accent bg-accent-faint" : "border-border bg-surface hover:border-accent-soft"
          }`}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Needs review</p>
          <p className="tnum mt-1 text-2xl font-semibold">{stats.unassigned}</p>
          <p className="text-xs text-muted">split not yet determined</p>
        </button>
      </section>

      <div className="mb-6 grid gap-3 lg:grid-cols-5">
        {/* Monthly trend */}
        <section
          aria-label="Monthly spend"
          className="rounded-xl border border-border bg-surface p-5 lg:col-span-3"
        >
          <h2 className="mb-4 text-sm font-medium text-muted">
            Monthly spend{category ? ` · ${category}` : ""} · {activeYear}
          </h2>
          <div className="flex h-40 items-end gap-1.5">
            {monthTotals.map((total, i) => {
              const m = i + 1;
              const selected = month === m;
              return (
                <button
                  key={m}
                  onClick={() => setMonth(selected ? null : m)}
                  className="group relative flex h-full flex-1 flex-col justify-end"
                  aria-label={`${MONTH_NAMES[i]}: ${fmtUSD(total)}`}
                >
                  <span className="pointer-events-none absolute -top-1 left-1/2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
                    {MONTH_NAMES[i]} · {fmtUSD(total)}
                  </span>
                  <span
                    className={`block w-full rounded-t-[4px] transition-colors ${
                      selected ? "bg-accent-deep" : total > 0 ? "bg-accent group-hover:bg-accent-deep" : "bg-border"
                    }`}
                    style={{ height: total > 0 ? `${Math.max((total / maxMonth) * 100, 2)}%` : "2px" }}
                  />
                  <span className={`mt-1.5 text-center text-[10px] ${selected ? "font-semibold text-accent-deep" : "text-muted"}`}>
                    {MONTH_NAMES[i].slice(0, 3)}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {/* Category breakdown */}
        <section
          aria-label="Spend by category"
          className="rounded-xl border border-border bg-surface p-5 lg:col-span-2"
        >
          <h2 className="mb-3 text-sm font-medium text-muted">By category</h2>
          <div className="flex max-h-48 flex-col gap-1 overflow-y-auto pr-1">
            {categoryTotals.map(([cat, total]) => {
              const selected = category === cat;
              return (
                <button
                  key={cat}
                  onClick={() => setCategory(selected ? null : cat)}
                  className={`rounded-lg px-2.5 py-1.5 text-left transition-colors ${
                    selected ? "bg-accent-faint" : "hover:bg-background"
                  }`}
                >
                  <span className="flex items-baseline justify-between gap-2 text-sm">
                    <span className={selected ? "font-medium text-accent-deep" : ""}>{cat}</span>
                    <span className="tnum text-muted">{fmtUSD(total)}</span>
                  </span>
                  <span className="mt-1 block h-1.5 w-full overflow-hidden rounded-full bg-background">
                    <span
                      className={`block h-full rounded-full ${selected ? "bg-accent-deep" : "bg-accent"}`}
                      style={{ width: `${Math.max((total / maxCategory) * 100, 1)}%` }}
                    />
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      </div>

      {/* Ledger */}
      <section aria-label="Transactions" className="rounded-xl border border-border bg-surface">
        <div className="flex items-center gap-2 border-b border-border px-5 py-3">
          <Search size={15} className="text-muted" />
          <input
            type="search"
            placeholder="Search merchant or card…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-transparent text-sm focus:outline-none"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-5 py-2.5 font-medium">Date</th>
                <th className="px-3 py-2.5 font-medium">Item</th>
                <th className="px-3 py-2.5 font-medium">Category</th>
                <th className="px-3 py-2.5 font-medium">Card</th>
                <th className="px-3 py-2.5 text-right font-medium">Charged</th>
                <th className="px-3 py-2.5 text-right font-medium">Owed to me</th>
                <th className="px-3 py-2.5 text-right font-medium">I owe</th>
                <th className="w-10 px-3 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {ledger.map((e) => (
                <tr
                  key={e.id}
                  onClick={() => setEditing(e)}
                  className="group cursor-pointer border-b border-border/60 last:border-0 hover:bg-accent-faint/60"
                >
                  <td className="tnum whitespace-nowrap px-5 py-2.5 text-muted">{fmtDate(e.date)}</td>
                  <td className="max-w-xs truncate px-3 py-2.5" title={e.item}>{e.item}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        e.category === "UNKNOWN"
                          ? "bg-amber-50 font-medium text-warn"
                          : "bg-background text-muted"
                      }`}
                    >
                      {e.category}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-muted">{e.paymentType}</td>
                  <td className="tnum whitespace-nowrap px-3 py-2.5 text-right text-muted">{fmtUSD(e.amountCharged)}</td>
                  <td className="tnum whitespace-nowrap px-3 py-2.5 text-right">
                    {e.othersOwe === null ? (
                      <span className="text-xs italic text-warn">TBD</span>
                    ) : e.othersOwe > 0 ? (
                      <span className="text-good">{fmtUSD(e.othersOwe)}</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="tnum whitespace-nowrap px-3 py-2.5 text-right font-medium">{fmtUSD(e.amountIOwe)}</td>
                  <td className="px-3 py-2.5 text-right">
                    <Pencil size={14} className="text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                  </td>
                </tr>
              ))}
              {ledger.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-10 text-center text-sm text-muted">
                    No transactions match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {editing && (
        <EditModal
          expense={editing}
          onClose={() => setEditing(null)}
          onSaved={(updated) => {
            setExpenses((prev) =>
              prev
                ? prev.map((e) =>
                    // Keep the client-resolved date/month — the PATCH response
                    // returns the raw Sheet cell, which may lack a year.
                    e.id === updated.id ? { ...updated, date: e.date, month: e.month } : e,
                  )
                : prev,
            );
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

interface StatTileProps {
  label: string;
  value: string;
  emphasis?: boolean;
}

function StatTile({ label, value, emphasis }: StatTileProps) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        emphasis ? "border-accent-soft bg-accent-faint" : "border-border bg-surface"
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`tnum mt-1 text-2xl font-semibold ${emphasis ? "text-accent-deep" : ""}`}>
        {value}
      </p>
    </div>
  );
}
