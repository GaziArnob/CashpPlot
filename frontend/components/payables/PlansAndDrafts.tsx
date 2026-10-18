"use client";

import { useState } from "react";
import { Check, Copy, FileText, Pencil, Trash2 } from "lucide-react";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { BillOption, NegotiationDraft, PaymentPlan, UpcomingBill } from "@/lib/types";
import ConfirmAction from "./ConfirmAction";
import PlanModal from "./PlanModal";

const STATUS_COLOR = {
  draft: "slate", approved: "blue", accepted: "green", rejected: "red", cancelled: "slate", completed: "green",
} as const;
const STATUS_HELP: Record<PaymentPlan["status"], string> = {
  draft: "Not approved yet. It changes nothing.",
  approved: "You approved proposing it. Waiting for the supplier's answer.",
  accepted: "The supplier agreed. Your cash forecast now follows this schedule.",
  rejected: "The supplier declined. Your forecast is unchanged.",
  cancelled: "Cancelled.", completed: "All installments paid.",
};

function useAction(onChanged: () => void) {
  const [error, setError] = useState<string | null>(null);
  async function run(path: string, body: object = {}, method = "POST") {
    setError(null);
    try {
      await api(path, { method, body: method === "DELETE" ? undefined : JSON.stringify(body) });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work");
      throw e;
    }
  }
  return { run, error };
}

function PlanCard({ p, bill, options, currency, onChanged }: {
  p: PaymentPlan; bill?: UpcomingBill; options: BillOption[]; currency: string; onChanged: () => void;
}) {
  const { run, error } = useAction(onChanged);
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const [busyDraft, setBusyDraft] = useState<string | null>(null);
  const final = ["rejected", "cancelled", "completed"].includes(p.status);

  async function draftMessage(lang: "en" | "bn") {
    setBusyDraft(lang);
    try { await run("/negotiation-drafts", { bill_id: p.bill_id, plan_id: p.id, lang }); } catch { /* shown below */ } finally { setBusyDraft(null); }
  }

  return (
    <li className="py-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{p.supplier} <span className="font-normal text-slate-500">· {money(p.bill_amount, currency)} bill</span></p>
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
            <Badge color={STATUS_COLOR[p.status]}>{p.status}</Badge>
            <Badge>{p.kind}</Badge>
            {p.affects_forecast && <Badge color="green">in your forecast</Badge>}
            <span className="text-slate-500">{STATUS_HELP[p.status]}</span>
          </p>
        </div>
        <p className="text-right text-xs text-slate-500">
          Paid {money(p.paid_so_far, currency)} · left {money(p.remaining, currency)}
          {p.estimated_fee > 0 && <><br />est. fee {money(p.estimated_fee, currency)}</>}
        </p>
      </div>

      <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
        {p.installments.map((i, k) => (
          <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
            <span>{k + 1}. {shortDate(i.due_date)}: <b className="tabular">{money(i.amount, currency)}</b></span>
            {i.status === "paid" ? <Badge color="green">paid {i.paid_date && shortDate(i.paid_date)}</Badge>
              : p.status === "accepted" ? (
                <ConfirmAction label="I paid this" prompt="Record that you paid it yourself? The app does not move money."
                  confirmLabel="Yes, I paid" onConfirm={() => run(`/payment-plans/installments/${i.id}/paid`, { confirm: true })} />
              ) : <span className="text-xs text-slate-400">scheduled</span>}
          </li>
        ))}
      </ul>
      {p.supplier_response_note && <p className="mt-2 text-xs text-slate-600">Supplier said: {p.supplier_response_note}</p>}

      {!final && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {(p.status === "draft" || p.status === "approved") && (
            <Button variant="secondary" onClick={() => setEditing(true)}><Pencil className="size-4" /> Edit</Button>
          )}
          {p.status === "draft" && (
            <ConfirmAction variant="primary" label="Approve this plan"
              prompt="Approve proposing this schedule to the supplier? Nothing is sent or paid."
              onConfirm={() => run(`/payment-plans/${p.id}/approve`, { confirm: true })} />
          )}
          {p.status === "approved" && (
            <>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Supplier's reply (optional)" maxLength={500}
                className="min-w-48 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm" />
              <ConfirmAction variant="primary" label="Supplier accepted" prompt="Record that the supplier agreed? Your forecast will follow this plan."
                onConfirm={() => run(`/payment-plans/${p.id}/supplier-response`, { accepted: true, note: note || null, confirm: true })} />
              <ConfirmAction label="Supplier declined" prompt="Record that the supplier declined?"
                onConfirm={() => run(`/payment-plans/${p.id}/supplier-response`, { accepted: false, note: note || null, confirm: true })} />
            </>
          )}
          <Button variant="ghost" disabled={busyDraft !== null} onClick={() => draftMessage("en")}><FileText className="size-4" />{busyDraft === "en" ? "…" : "Message (EN)"}</Button>
          <Button variant="ghost" disabled={busyDraft !== null} onClick={() => draftMessage("bn")}><FileText className="size-4" />{busyDraft === "bn" ? "…" : "বাংলা message"}</Button>
          <ConfirmAction variant="ghost" label="Cancel plan" prompt="Cancel this plan?" confirmLabel="Yes, cancel it"
            onConfirm={() => run(`/payment-plans/${p.id}/cancel`)} />
        </div>
      )}
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      {editing && (
        <PlanModal plan={p} currency={currency} options={options} onClose={() => setEditing(false)} onSaved={onChanged}
          bill={{ bill_id: p.bill_id, supplier: p.supplier, outstanding: p.bill_outstanding, due_date: bill?.due_date ?? p.installments[0]?.due_date }} />
      )}
    </li>
  );
}

export function PlansSection({ bills, optionsByBill, currency, onChanged, refreshKey }: {
  bills: UpcomingBill[]; optionsByBill: Map<number, BillOption[]>; currency: string; onChanged: () => void;
  refreshKey: number;
}) {
  // `_` is ignored by the API; changing it reloads the list after any plan or draft change on the page.
  const plans = useApi<PaymentPlan[]>(`/payment-plans?_=${refreshKey}`);
  const reload = onChanged;
  return (
    <Card>
      <CardTitle>Payment plans</CardTitle>
      {plans.loading && !plans.data ? <Loading /> : plans.error ? <ErrorBox message={plans.error} onRetry={plans.reload} />
        : plans.data && plans.data.length > 0 ? (
          <ul className="divide-y divide-slate-100">
            {plans.data.map((p) => (
              <PlanCard key={p.id} p={p} currency={currency} onChanged={reload}
                bill={bills.find((b) => b.bill_id === p.bill_id)} options={optionsByBill.get(p.bill_id) ?? []} />
            ))}
          </ul>
        ) : <p className="text-sm text-slate-500">No plans yet. Use “Plan” next to an upcoming bill to start a draft.</p>}
    </Card>
  );
}

function DraftCard({ d, onChanged }: { d: NegotiationDraft; onChanged: () => void }) {
  const [text, setText] = useState(d.message);
  const [saved, setSaved] = useState(true);
  const [copied, setCopied] = useState(false);
  const { run, error } = useAction(onChanged);
  async function save() {
    await run(`/negotiation-drafts/${d.id}`, { message: text }, "PUT");
    setSaved(true);
  }
  return (
    <li className="py-4">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <Badge color={d.status === "marked_sent" ? "green" : "slate"}>{d.status === "marked_sent" ? "you sent it" : "draft"}</Badge>
        <Badge color="blue">{d.lang === "bn" ? "বাংলা" : "English"}</Badge>
        <span className="text-slate-500">{d.generated_by.startsWith("template") ? "from a template" : `written with AI (${d.generated_by.split(":")[0]})`}</span>
      </div>
      <textarea value={text} onChange={(e) => { setText(e.target.value); setSaved(false); }} rows={9}
        className="w-full rounded-lg border border-slate-300 p-3 text-sm leading-relaxed outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button variant="secondary" disabled={saved} onClick={() => save().catch(() => undefined)}>{saved ? "Saved" : "Save edits"}</Button>
        <Button variant="secondary" onClick={async () => {
          try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
        }}>{copied ? <Check className="size-4" /> : <Copy className="size-4" />} {copied ? "Copied" : "Copy"}</Button>
        {d.status === "draft" && (
          <ConfirmAction label="I sent it" prompt="Mark this as sent? The app never sends messages; this only records that you did."
            confirmLabel="Yes, I sent it" onConfirm={() => run(`/negotiation-drafts/${d.id}/mark-sent`, { confirm: true })} />
        )}
        <Button variant="ghost" onClick={() => run(`/negotiation-drafts/${d.id}`, {}, "DELETE").catch(() => undefined)}><Trash2 className="size-4" /> Delete</Button>
      </div>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
    </li>
  );
}

export function DraftsSection({ refreshKey }: { refreshKey: number }) {
  // `_` is ignored by the API; changing it makes the list reload when a plan creates a new draft.
  const drafts = useApi<NegotiationDraft[]>(`/negotiation-drafts?_=${refreshKey}`);
  return (
    <Card>
      <CardTitle right={<Badge color="amber">drafts only: never sent by the app</Badge>}>Supplier messages</CardTitle>
      {drafts.loading && !drafts.data ? <Loading /> : drafts.error ? <ErrorBox message={drafts.error} onRetry={drafts.reload} />
        : drafts.data && drafts.data.length > 0 ? (
          <ul className="divide-y divide-slate-100">
            {drafts.data.map((d) => <DraftCard key={d.id} d={d} onChanged={drafts.reload} />)}
          </ul>
        ) : <p className="text-sm text-slate-500">No messages yet. Open a plan and choose “Message (EN)” or “বাংলা message”. You can edit it before using it.</p>}
    </Card>
  );
}
