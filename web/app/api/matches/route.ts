import { NextRequest, NextResponse } from "next/server";
import { applyMatchToSheet, getExpenses, getUnmatched } from "@/lib/sheets";
import { appendMatch } from "@/lib/matches";
import { rankCandidates } from "@/lib/matching";
import { NOT_ON_CARD } from "@/lib/types";

export const dynamic = "force-dynamic";

// GET → every unmatched Splitwise expense with its ranked card candidates.
export async function GET() {
  try {
    const [expenses, unmatched] = await Promise.all([getExpenses(), getUnmatched()]);
    // Candidates: card charges whose split is still undetermined (blank
    // "Other people Owe me"). Anything already split, solo (0), or sourced
    // from Splitwise itself is not a match target.
    const eligible = expenses.filter(
      (e) =>
        e.othersOwe === null &&
        !e.paymentType.toLowerCase().includes("splitwise"),
    );
    return NextResponse.json({
      unmatched: unmatched.map((u) => ({
        ...u,
        candidates: rankCandidates(u, eligible),
      })),
    });
  } catch (e) {
    // The tab is created by the CLI export — before the first export there is
    // simply nothing to match yet.
    if (String(e).includes(`Tab "Unmatched Splitwise" not found`)) {
      return NextResponse.json({ unmatched: [], missingTab: true });
    }
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

// POST body: { splitwiseId: string, cardId: string, cardGuard?: {date, item} }
// cardId may be "__not_on_card__" (paid via Venmo/cash; stop suggesting it).
export async function POST(req: NextRequest) {
  try {
    const { splitwiseId, cardId, cardGuard } = (await req.json()) ?? {};
    if (typeof splitwiseId !== "string" || !splitwiseId || typeof cardId !== "string" || !cardId) {
      return NextResponse.json(
        { error: "splitwiseId and cardId are required" },
        { status: 400 },
      );
    }
    const swIdNum = Number(splitwiseId);
    if (!Number.isFinite(swIdNum)) {
      return NextResponse.json({ error: "splitwiseId must be numeric" }, { status: 400 });
    }
    const isCardMatch = cardId !== NOT_ON_CARD;
    if (isCardMatch && (typeof cardGuard?.item !== "string" || typeof cardGuard?.amountCharged !== "number")) {
      return NextResponse.json({ error: "cardGuard {item, amountCharged} is required" }, { status: 400 });
    }

    // Sheet first (it can fail), then the local match file. The match file
    // entry is what keeps this Splitwise expense out of future unmatched
    // exports; the Sheet row itself carries the split amounts.
    await applyMatchToSheet(cardId, isCardMatch ? cardGuard : null, splitwiseId);
    appendMatch(swIdNum, isCardMatch ? `__ui_row__:${cardId}` : NOT_ON_CARD);
    return NextResponse.json({ ok: true });
  } catch (e) {
    const msg = String(e);
    const status = msg.includes("not found") ? 404 : msg.includes("stale row") ? 409 : 500;
    return NextResponse.json({ error: msg }, { status });
  }
}
