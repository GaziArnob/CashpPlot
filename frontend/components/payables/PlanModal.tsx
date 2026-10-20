"use client";

import { createPortal } from "react-dom";
import { useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
import { Badge, Button, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import type { BillOption, PaymentPlan } from "@/lib/types";

type Row = { due_date: string; amount: string };

const KIND_LABEL = { pay_on_time: "Pay on time", extension: "Ask for an extension", partial: "Pay in parts" } as const;

function toRows(items: { due_date: string; amount: number }[]): Row[] {
  return items.map((i) => ({ due_date: i.due_date, amount: String(i.amount) }));
}

/** Create a payment plan from a suggested option (or edit an existing draft). Always saved as a DRAFT. */
export default function PlanModal({ bill, options, plan, currency, onClose, onSaved }: {
  bill: { bill_id: number; supplier: string; outstanding: number; due_date: string };
  options: BillOption[]; plan?: PaymentPlan; currency: string; onClose: () => void; onSaved: () => void;
}) {
  const suggestions = options.filter((o) => o.kind !== "pay_on_time");
  const first = suggestions.find((o) => o.keeps_cash_safe) ?? suggestions[0];
  const [kind, setKind] = useState<"extension" | "partial" | "custom">(plan?.kind ?? first?.kind as "extension" | "partial" ?? "custom");
  const [rows, setRows] = useState<Row[]>(plan ? toRows(plan.installments) : first ? toRows(first.installments) : [{ due_date: "", amount: String(bill.outstanding) }]);
  const [note, setNote] = useState(plan?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const total = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const diff = Math.round((bill.outstanding - total) * 100) / 100;

  function pick(o: BillOption) {
    setKind(o.kind as "extension" | "partial");
    setRows(toRows(o.installments));
  }
  function update(i: number, patch: Partial<Row>) {
    setKind("custom");
    setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const installments = rows.map((r) => ({ due_date: r.due_date, amount: Number(r.amount) }));
      if (plan) await api(`/payment-plans/${plan.id}`, { method: "PUT", body: JSON.stringify({ installments, note: note || null }) });
      else await api("/payment-plans", { method: "POST", body: JSON.stringify({ bill_id: bill.bill_id, kind, installments, note: note || null }) });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the plan");
    } finally {
      setBusy(false);
    }
  }

  if (typeof document === "undefined") return null;
  // Rendered on <body>: inside a card (which has a transform and a blur) a fixed overlay would be sized to that card.
  return createPortal(
    <div className="ff-fade fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="ff-pop max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="font-semibold">{plan ? "Edit payment plan" : "New payment plan"}: {bill.supplier}</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              {money(bill.outstanding, currency)} owed, due {shortDate(bill.due_date)}. This only saves a draft. Nothing is paid or sent.
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X className="size-5" /></button>
        </div>

        {!plan && suggestions.length > 0 && (
          <div className="mb-4 grid gap-2 sm:grid-cols-2">
            {suggestions.map((o) => (
              <button key={o.kind} onClick={() => pick(o)}
                className={`rounded-lg border p-3 text-left text-sm ${kind === o.kind ? "border-emerald-500 bg-emerald-50" : "border-slate-200 hover:border-slate-300"}`}>
                <p className="font-medium">{KIND_LABEL[o.kind]}</p>
                <p className="mt-1 text-xs text-slate-600">{o.reasoning}</p>
                <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                  {o.keeps_cash_safe ? <Badge color="green">keeps cash safe</Badge> : <Badge color="amber">{o.days_below_after} days still tight</Badge>}
                  <span className="text-slate-500">est. cost {money(o.estimated_fee, currency)}</span>
                </p>
              </button>
            ))}
          </div>
        )}

        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Installments (editable)</p>
        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <span className="w-5 text-xs text-slate-400">{i + 1}.</span>
              <input type="date" value={r.due_date} onChange={(e) => update(i, { due_date: e.target.value })}
                className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm" />
              <input value={r.amount} inputMode="decimal" onChange={(e) => update(i, { amount: e.target.value.replace(/[^0-9.]/g, "") })}
                className="w-36 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm tabular" />
              {rows.length > 1 && (
                <button onClick={() => { setKind("custom"); setRows((rs) => rs.filter((_, k) => k !== i)); }}
                  className="text-slate-400 hover:text-rose-600" aria-label="Remove installment"><Trash2 className="size-4" /></button>
              )}
            </div>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <Button variant="ghost" onClick={() => { setKind("custom"); setRows((rs) => [...rs, { due_date: "", amount: "" }]); }}>
            <Plus className="size-4" /> Add installment
          </Button>
          <p className={`text-sm tabular ${diff === 0 ? "text-emerald-700" : "text-rose-600"}`}>
            {diff === 0 ? "Adds up to the amount owed" : diff > 0 ? `${money(diff, currency)} still to schedule` : `${money(-diff, currency)} too much`}
          </p>
        </div>

        <label className="mt-4 block text-sm">
          <span className="text-slate-600">Note (optional)</span>
          <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
        </label>
        {error && <div className="mt-3"><ErrorBox message={error} /></div>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || diff !== 0 || rows.some((r) => !r.due_date || !Number(r.amount))}>
            {busy ? "Saving…" : plan ? "Save changes" : "Save as draft"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
