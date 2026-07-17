"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Check, CircleSlash } from "lucide-react";
import { fmtDate, fmtUSD } from "@/lib/format";
import { NOT_ON_CARD, type Candidate, type Unmatched } from "@/lib/types";

type UnmatchedWithCandidates = Unmatched & { candidates: Candidate[] };

export default function MatchesPage() {
  const [items, setItems] = useState<UnmatchedWithCandidates[] | null>(null);
  const [missingTab, setMissingTab] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/matches")
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
        setItems(data.unmatched);
        setMissingTab(Boolean(data.missingTab));
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  async function confirm(splitwiseId: string, cardId: string, cardGuard?: { item: string; amountCharged: number }) {
    setBusyId(splitwiseId);
    setActionError(null);
    try {
      const res = await fetch("/api/matches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ splitwiseId, cardId, cardGuard }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      setItems((prev) => prev?.filter((u) => u.splitwiseId !== splitwiseId) ?? null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Match failed");
    } finally {
      setBusyId(null);
    }
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-border bg-surface p-6">
        <p className="mb-1 flex items-center gap-2 font-medium text-red-600">
          <AlertCircle size={16} /> Couldn’t load unmatched expenses
        </p>
        <p className="text-sm text-muted">{loadError}</p>
      </div>
    );
  }

  if (!items) {
    return <p className="text-sm text-muted">Loading unmatched Splitwise expenses…</p>;
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Splitwise matches</h1>
        <p className="text-sm text-muted">
          {missingTab
            ? "No Splitwise data in the Sheet yet — run `python -m src.main export` to publish it, then reload."
            : items.length === 0
              ? "Everything is matched — nothing to do."
              : `${items.length} shared expense${items.length === 1 ? "" : "s"} you paid on Splitwise, not yet tied to a card charge.`}
        </p>
      </header>

      {actionError && (
        <p className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          <AlertCircle size={15} /> {actionError}
        </p>
      )}

      <div className="flex flex-col gap-4">
        {items.map((u) => (
          <section
            key={u.splitwiseId}
            aria-label={u.description}
            className={`rounded-xl border border-border bg-surface p-5 ${
              busyId === u.splitwiseId ? "opacity-60" : ""
            }`}
          >
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h2 className="font-semibold">{u.description}</h2>
                <p className="text-sm text-muted">
                  {fmtDate(u.date)} · you paid <span className="tnum">{fmtUSD(u.youPaid)}</span>
                  {" · "}your share <span className="tnum">{fmtUSD(u.yourShare)}</span>
                  {" · "}others owe <span className="tnum text-good">{fmtUSD(u.othersOweYou)}</span>
                </p>
              </div>
              <button
                onClick={() => confirm(u.splitwiseId, NOT_ON_CARD)}
                disabled={busyId !== null}
                className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:border-foreground/30 hover:text-foreground disabled:opacity-50"
              >
                <CircleSlash size={13} /> Not on a card (Venmo/cash)
              </button>
            </div>

            {u.candidates.length === 0 ? (
              <p className="rounded-lg bg-background px-4 py-3 text-sm text-muted">
                No likely card charges found.
              </p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {u.candidates.map((c) => (
                  <li
                    key={c.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border/70 px-3 py-2 hover:border-accent-soft hover:bg-accent-faint/50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm" title={c.item}>{c.item}</p>
                      <p className="text-xs text-muted">
                        {fmtDate(c.date)} · {c.paymentType} ·{" "}
                        <span className="tnum">{fmtUSD(c.amountCharged)}</span>
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span
                        className="tnum rounded-full bg-background px-2 py-0.5 text-xs text-muted"
                        title="Match confidence (amount, description, date)"
                      >
                        {Math.round(c.score)}
                      </span>
                      <button
                        onClick={() => confirm(u.splitwiseId, c.id, { item: c.item, amountCharged: c.amountCharged })}
                        disabled={busyId !== null}
                        className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-deep disabled:opacity-50"
                      >
                        <Check size={13} /> Match
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
