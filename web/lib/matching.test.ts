// Run with: node --test lib/matching.test.ts  (Node 22.6+ strips types natively)
import assert from "node:assert";
import { test } from "node:test";
import { rankCandidates } from "./matching.ts";
import type { Expense, Unmatched } from "./types.ts";

const expense = (over: Partial<Expense>): Expense => ({
  id: "x", date: "2026-05-07", month: "May", category: "Misc", item: "",
  paymentType: "Amex", amountCharged: 0, othersOwe: null, amountIOwe: 0,
  notes: "", ...over,
});

const unmatched: Unmatched = {
  date: "2026-05-07",
  description: "Boho Karaoke",
  totalCost: 80,
  youPaid: 80,
  yourShare: 20,
  othersOweYou: 60,
  splitwiseId: "1",
};

test("exact amount + desc + date outranks unrelated same-day charge", () => {
  const good = expense({ id: "good", item: "BOHO KARAOKE WEST 4TH", amountCharged: 80 });
  const noise = expense({ id: "noise", item: "DUANE READE", amountCharged: 80 });
  const far = expense({ id: "far", item: "BOHO KARAOKE", amountCharged: 200, date: "2026-06-30" });

  const ranked = rankCandidates(unmatched, [noise, far, good]);
  assert.equal(ranked[0].id, "good");
  // 50 (amount) + 30 (full desc overlap) + 20 (same day) = 100
  assert.equal(Math.round(ranked[0].score), 100);
  // 'far' is >20 days and >50% off on amount: only desc score survives
  const farScore = ranked.find((c) => c.id === "far");
  assert.ok(!farScore || Math.round(farScore.score) === 30);
});

test("zero-signal transactions are excluded", () => {
  const junk = expense({ item: "ZZZ", amountCharged: 999, date: "2025-01-01" });
  assert.deepEqual(rankCandidates(unmatched, [junk]), []);
});
