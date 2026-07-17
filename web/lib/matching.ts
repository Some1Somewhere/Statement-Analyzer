// Candidate ranking for Splitwise matching — a direct port of
// rank_candidates() in src/splitwise_matcher.py. Keep the two in sync.
import type { Candidate, Expense, Unmatched } from "./types";

const STOP_TOKENS = new Set([
  "the", "at", "on", "in", "and", "or", "with", "for", "to", "a", "an",
  "of", "my", "our", "your", "from", "is", "was", "by",
]);

function tokenize(text: string): Set<string> {
  const tokens = text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return new Set(tokens.filter((t) => t.length > 1 && !STOP_TOKENS.has(t)));
}

/** Shared-token overlap coefficient (|shared| / |smaller set|), not Jaccard,
 *  so card-side chaff like store locations is not penalised. */
function descriptionScore(swDesc: string, cardDesc: string, maxScore: number): number {
  if (!swDesc || !cardDesc) return 0;
  const sw = tokenize(swDesc);
  const card = tokenize(cardDesc);
  if (sw.size === 0 || card.size === 0) return 0;
  let overlap = 0;
  for (const t of sw) if (card.has(t)) overlap++;
  if (overlap === 0) return 0;
  return maxScore * (overlap / Math.min(sw.size, card.size));
}

const DAY_MS = 86_400_000;

/**
 * Scoring (max 100): amount similarity 50 (vs what you actually paid),
 * description overlap 30, date proximity 20 (loses 1/day over a 20-day window).
 */
export function rankCandidates(
  unmatched: Unmatched,
  expenses: Expense[],
  topN = 5,
): Candidate[] {
  const matchAmount = unmatched.youPaid > 0 ? unmatched.youPaid : unmatched.totalCost;
  const swDate = Date.parse(unmatched.date);
  if (Number.isNaN(swDate)) return [];

  const scored: Candidate[] = [];
  for (const e of expenses) {
    const txnDate = Date.parse(e.date);
    if (Number.isNaN(txnDate)) continue;

    const dayDiff = Math.abs(Math.round((txnDate - swDate) / DAY_MS));
    const dateScore = Math.max(0, 20 - dayDiff);

    const pctDiff =
      matchAmount > 0 ? Math.abs(e.amountCharged - matchAmount) / matchAmount : Infinity;
    const amountScore = matchAmount > 0 ? Math.max(0, 50 - pctDiff * 100) : 0;

    const descScore = descriptionScore(unmatched.description, e.item, 30);

    const score = dateScore + amountScore + descScore;
    if (score > 0) {
      scored.push({
        id: e.id,
        date: e.date,
        item: e.item,
        paymentType: e.paymentType,
        amountCharged: e.amountCharged,
        score,
      });
    }
  }
  return scored.sort((a, b) => b.score - a.score).slice(0, topN);
}
