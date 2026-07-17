// Reads/writes data/splitwise_matches.json — the same file the Python CLI
// uses, so matches made in the UI and in `match-splitwise` stay in one place.
import fs from "node:fs";
import path from "node:path";
import type { Match } from "./types";

const MATCHES_FILE = path.resolve(
  process.cwd(),
  "..",
  "data",
  "splitwise_matches.json",
);

export function loadMatches(): Match[] {
  if (!fs.existsSync(MATCHES_FILE)) return [];
  // Matches are hand-built user work — a corrupt file should fail loudly,
  // not be silently replaced (mirrors load_matches in splitwise_matcher.py).
  return JSON.parse(fs.readFileSync(MATCHES_FILE, "utf8"));
}

export function appendMatch(splitwiseId: number, cardId: string): Match[] {
  const matches = [
    ...loadMatches(),
    {
      splitwise_id: splitwiseId,
      card_transaction_id: cardId,
      matched_at: new Date().toISOString(),
    },
  ];
  fs.writeFileSync(MATCHES_FILE, JSON.stringify(matches, null, 2));
  return matches;
}
