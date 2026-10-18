"use client";

import { useState } from "react";
import { MessageSquareText } from "lucide-react";
import ReminderModal from "@/components/ReminderModal";
import { Badge, Button, Card, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate, money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Bill, CollectionPriority, RecoveryCustomer, Reminder } from "@/lib/types";

const ACTION_COLOR = {
  stop_credit: "red", visit: "red", call: "amber", discount: "blue", send_reminder: "slate", wait: "green",
} as const;
const BUCKET_LABEL = { current: "Not due", "0-30": "1-30 days", "31-60": "31-60 days", "61-90": "61-90 days", "90+": "90+ days" };

export default function LedgerPage() {
  const [tab, setTab] = useState<"receivables" | "payables">("receivables");
  return (
    <>
      <PageHeader title="Ledger" subtitle="Who owes you, and who you owe"
        right={
          <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5">
            {(["receivables", "payables"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${tab === t ? "bg-emerald-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>
                {t === "receivables" ? "They owe me" : "I owe"}
              </button>
            ))}
          </div>
        } />
      {tab === "receivables" ? <Receivables /> : <Payables />}
    </>
  );
}

function Receivables() {
  const { data, error, loading, reload } = useApi<CollectionPriority>("/collections/priority");
  const [draft, setDraft] = useState<{ reminder: Reminder; customer: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function makeDraft(c: RecoveryCustomer) {
    setBusy(String(c.customer_id));
    setActionError(null);
    try {
      const reminder = await api<Reminder>(`/collections/${c.customer_id}/reminder`, { method: "POST" });
      setDraft({ reminder, customer: c.customer_name });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not draft a reminder");
    } finally {
      setBusy(null);
    }
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;

  return (
    <>
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Outstanding" value={money(data.total_outstanding)} />
        <Stat label="Overdue" value={money(data.total_overdue)} tone="warn" />
        <Stat label="Likely in next 7 days" value={money(data.expected_in_7_days)} tone="good"
          hint="Sum of each balance x its probability" />
        <Stat label="Cash gap to cover" value={data.shortage_gap ? money(data.shortage_gap) : "None"}
          tone={data.shortage_gap ? "bad" : "good"} />
      </div>
      {actionError && <div className="mb-4"><ErrorBox message={actionError} /></div>}
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[920px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-5 py-3 font-medium">Score</th>
              <th className="px-3 py-3 font-medium">Customer</th>
              <th className="px-3 py-3 text-right font-medium">Owed</th>
              <th className="px-3 py-3 text-right font-medium">Pays in 7d</th>
              <th className="px-3 py-3 font-medium">Recommended action</th>
              <th className="px-3 py-3 text-right font-medium">Credit limit</th>
              <th className="px-5 py-3 text-right font-medium">Reminder</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.customers.map((c) => (
              <tr key={c.customer_id} className="align-top hover:bg-slate-50">
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span className="w-8 text-right font-semibold tabular">{Math.round(c.score)}</span>
                    <div className="h-1.5 w-14 rounded-full bg-slate-100">
                      <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${c.score}%` }} />
                    </div>
                  </div>
                </td>
                <td className="px-3 py-3">
                  <p className="font-medium">
                    {c.customer_name}{" "}
                    {c.new_customer && <Badge color="blue">new</Badge>}{" "}
                    {c.relationship.top_customer && <Badge color="green">top customer</Badge>}
                  </p>
                  <p className="text-xs text-slate-500">
                    {BUCKET_LABEL[c.aging_bucket]}
                    {c.max_days_overdue > 0 && ` · ${c.max_days_overdue} days overdue`}
                    {c.history.on_time_rate !== null && ` · ${Math.round(c.history.on_time_rate * 100)}% on time`}
                    {c.history.avg_delay_days !== null && c.history.avg_delay_days > 0 &&
                      ` · avg ${Math.round(c.history.avg_delay_days)}d late`}
                    {c.closes_shortage && <span className="ml-1 text-rose-600">· closes cash gap</span>}
                  </p>
                </td>
                <td className="px-3 py-3 text-right tabular">
                  <p className="font-medium">{money(c.outstanding)}</p>
                  {c.overdue_amount > 0 && <p className="text-xs text-rose-600">{money(c.overdue_amount)} overdue</p>}
                </td>
                <td className="px-3 py-3 text-right font-medium tabular">{Math.round(c.p_pay_7d * 100)}%</td>
                <td className="px-3 py-3">
                  <Badge color={ACTION_COLOR[c.action]}>{c.action_label}</Badge>
                  {c.softened_for_relationship && (
                    <p className="mt-1 text-xs text-slate-500">Softened to protect a top relationship</p>
                  )}
                </td>
                <td className="px-3 py-3 text-right tabular" title={c.credit_limit_basis}>
                  {c.credit_limit === 0 ? <span className="text-rose-600">Stop credit</span> : money(c.credit_limit)}
                </td>
                <td className="px-5 py-3">
                  <div className="flex justify-end gap-1.5">
                    <Button variant="secondary" onClick={() => makeDraft(c)} disabled={busy !== null} className="px-2.5">
                      <MessageSquareText className="size-4" />
                      {busy === String(c.customer_id) ? "…" : "Draft reminder"}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="mt-3 text-xs text-slate-500">
        Score = 30% amount + 25% aging + 15% payment-history risk + 15% share of the cash gap it covers + 15% chance of
        paying within 7 days. Payment chance from {data.model.method === "logistic_regression"
          ? `a logistic regression trained on ${data.model.samples} past invoice-weeks` : "rules (not enough history yet)"}.
      </p>
      {draft && <ReminderModal draft={draft} onClose={() => setDraft(null)} />}
    </>
  );
}

function Payables() {
  const { data, error, loading, reload } = useApi<Bill[]>("/bills?status=unpaid");
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;
  const total = data.reduce((s, b) => s + b.amount, 0);
  return (
    <>
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Stat label="Bills to pay" value={money(total)} tone="warn" />
        <Stat label="Next due" value={data[0] ? longDate(data[0].due_date) : "—"} hint={data[0] ? `${data[0].supplier_name}, ${money(data[0].amount)}` : undefined} />
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-5 py-3 font-medium">Supplier</th>
              <th className="px-3 py-3 font-medium">Due</th>
              <th className="px-3 py-3 font-medium">Note</th>
              <th className="px-5 py-3 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((b) => (
              <tr key={b.id}>
                <td className="px-5 py-3 font-medium">{b.supplier_name}</td>
                <td className="px-3 py-3">{longDate(b.due_date)}</td>
                <td className="px-3 py-3 text-slate-500">{b.note ?? "—"}</td>
                <td className="px-5 py-3 text-right font-semibold tabular">{money(b.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
