"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Circle, CircleCheck, CircleSlash, RotateCcw } from "lucide-react";
import { Badge, Button, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import type { ActionPlan as Plan, PlanAction } from "@/lib/types";

const KIND_LABEL: Record<PlanAction["kind"], string> = {
  collect: "Collect", clear_stock: "Clear stock", delay_payable: "Delay payable", cut_expense: "Cut expense",
  scale_up: "Scale up", financing: "Financing",
};
const RISK_COLOR = { low: "green", medium: "amber", high: "red" } as const;

function ActionRow({ a, onChanged }: { a: PlanAction; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [doneForm, setDoneForm] = useState(false);
  const [actual, setActual] = useState(a.cash_impact > 0 ? String(Math.round(a.cash_impact)) : "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function call(path: string, body?: object) {
    setBusy(true);
    setError(null);
    try {
      await api(`/actions/${a.id}/${path}`, { method: "POST", body: JSON.stringify(body ?? {}) });
      setDoneForm(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the action");
    } finally {
      setBusy(false);
    }
  }

  const finished = a.status !== "open";
  return (
    <li className={`py-3 ${finished ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-3">
        <button
          onClick={() => (a.status === "open" ? setDoneForm((v) => !v) : call("reopen"))}
          disabled={busy} className="mt-0.5 text-slate-400 hover:text-emerald-600"
          aria-label={a.status === "open" ? "Mark done" : "Reopen"}>
          {a.status === "done" ? <CircleCheck className="size-5 text-emerald-600" />
            : a.status === "dismissed" ? <CircleSlash className="size-5" /> : <Circle className="size-5" />}
        </button>
        <div className="min-w-0 flex-1">
          <button onClick={() => setOpen((v) => !v)} className="flex w-full items-start gap-1 text-left">
            {open ? <ChevronDown className="mt-0.5 size-4 shrink-0 text-slate-400" />
              : <ChevronRight className="mt-0.5 size-4 shrink-0 text-slate-400" />}
            <span className={`text-sm font-medium ${a.status === "done" ? "line-through" : ""}`}>{a.title}</span>
          </button>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 pl-5 text-xs text-slate-500">
            <Badge>{KIND_LABEL[a.kind]}</Badge>
            <Badge color={RISK_COLOR[a.risk]}>{a.risk} risk</Badge>
            <span>lands in {a.days_to_impact} days</span>
            {a.optional && <Badge color="blue">optional</Badge>}
            {a.data.lands_after_shortage && !finished && <span className="text-amber-700">· after the first shortage</span>}
            {a.status === "done" && a.actual_amount !== null && <span className="text-emerald-700">· got {money(a.actual_amount)}</span>}
          </div>
          {open && <p className="mt-2 pl-5 text-sm leading-relaxed text-slate-600">{a.reasoning}</p>}
          {doneForm && (
            <div className="mt-3 flex flex-wrap items-end gap-2 pl-5">
              <label className="text-xs text-slate-600">
                Actual amount (optional)
                <input value={actual} onChange={(e) => setActual(e.target.value.replace(/[^0-9.-]/g, ""))} inputMode="decimal"
                  className="mt-1 block w-36 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm" />
              </label>
              <label className="flex-1 text-xs text-slate-600">
                Note
                <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500}
                  className="mt-1 block w-full min-w-40 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm" />
              </label>
              <Button disabled={busy} onClick={() => call("mark-done", {
                actual_amount: actual === "" ? null : Number(actual), note: note || null,
              })}>Mark done</Button>
              <Button variant="ghost" disabled={busy} onClick={() => call("dismiss", { note: note || null })}>Dismiss</Button>
            </div>
          )}
          {error && <div className="mt-2 pl-5"><ErrorBox message={error} /></div>}
        </div>
        <div className="shrink-0 text-right">
          <p className={`text-sm font-semibold tabular ${a.cash_impact > 0 ? "text-emerald-700" : a.cash_impact < 0 ? "text-rose-600" : "text-slate-400"}`}>
            {a.cash_impact > 0 ? "+" : a.cash_impact < 0 ? "−" : ""}{a.cash_impact === 0 ? "later" : money(Math.abs(a.cash_impact))}
          </p>
          {finished && (
            <button onClick={() => call("reopen")} disabled={busy}
              className="mt-1 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700">
              <RotateCcw className="size-3" /> reopen
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

export default function ActionPlan({ plan, onChanged }: { plan: Plan; onChanged: () => void }) {
  const needed = plan.actions.filter((a) => !a.optional);
  const optional = plan.actions.filter((a) => a.optional);
  const pct = plan.gap ? Math.min(100, Math.round((100 * plan.expected_from_plan) / plan.gap)) : 100;
  return (
    <>
      <div className="mb-4">
        <div className="mb-1 flex justify-between text-xs text-slate-600">
          <span>Plan brings in {money(plan.expected_from_plan)} of the {money(plan.gap)} needed</span>
          <span>{plan.done_count} done{plan.realized_so_far ? ` · ${money(plan.realized_so_far)} received` : ""}</span>
        </div>
        <div className="h-2 rounded-full bg-slate-100">
          <div className={`ff-grow h-2 rounded-full ${plan.gap_covered ? "bg-emerald-500" : "bg-amber-500"}`} style={{ width: `${pct}%` }} />
        </div>
        {!plan.gap_covered && <p className="mt-1 text-xs text-rose-600">{money(plan.remaining_gap)} still missing</p>}
      </div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Needed to cover the gap</p>
      <ul className="divide-y divide-slate-100">
        {needed.map((a) => <ActionRow key={a.id} a={a} onChanged={onChanged} />)}
        {needed.length === 0 && <li className="py-3 text-sm text-slate-500">Nothing urgent. The optional steps below are good practice.</li>}
      </ul>
      {optional.length > 0 && (
        <>
          <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Optional</p>
          <ul className="divide-y divide-slate-100">
            {optional.map((a) => <ActionRow key={a.id} a={a} onChanged={onChanged} />)}
          </ul>
        </>
      )}
    </>
  );
}
