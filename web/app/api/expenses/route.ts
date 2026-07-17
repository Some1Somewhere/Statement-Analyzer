import { NextRequest, NextResponse } from "next/server";
import { getExpenses, patchExpense } from "@/lib/sheets";
import { CATEGORIES } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json({ expenses: await getExpenses() });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

// PATCH body: { id, guard: {date, item}, patch: { category?, amountIOwe?, othersOwe?, notes? } }
export async function PATCH(req: NextRequest) {
  try {
    const body = await req.json();
    const { id, guard, patch } = body ?? {};
    if (typeof id !== "string" || !id || typeof patch !== "object" || !patch) {
      return NextResponse.json({ error: "id and patch are required" }, { status: 400 });
    }
    if (typeof guard?.item !== "string" || typeof guard?.amountCharged !== "number") {
      return NextResponse.json({ error: "guard {item, amountCharged} is required" }, { status: 400 });
    }
    if (patch.category !== undefined && !CATEGORIES.includes(patch.category)) {
      return NextResponse.json({ error: `Unknown category: ${patch.category}` }, { status: 400 });
    }
    for (const field of ["amountIOwe", "othersOwe"] as const) {
      const v = patch[field];
      if (v !== undefined && v !== null && (typeof v !== "number" || !Number.isFinite(v) || v < 0)) {
        return NextResponse.json({ error: `${field} must be a non-negative number` }, { status: 400 });
      }
    }
    const expense = await patchExpense(id, guard, {
      category: patch.category,
      amountIOwe: patch.amountIOwe,
      othersOwe: patch.othersOwe,
      notes: patch.notes === undefined ? undefined : String(patch.notes),
    });
    return NextResponse.json({ expense });
  } catch (e) {
    const msg = String(e);
    const status = msg.includes("not found") ? 404 : msg.includes("stale row") ? 409 : 500;
    return NextResponse.json({ error: msg }, { status });
  }
}
