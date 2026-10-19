"use client";

import { useState } from "react";
import { MessageSquareText, Plus } from "lucide-react";
import PlanModal from "@/components/payables/PlanModal";
import { AddBillModal, AddInvoiceModal, AddSupplierModal, RecordPaymentModal } from "@/components/QuickAdd";
import ReminderModal from "@/components/ReminderModal";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate, money } from "@/lib/format";
import { useApi, useBusiness } from "@/lib/hooks";
import type { Bill, CollectionPriority, RecoveryCustomer, Reminder } from "@/lib/types";

type OpenInvoice = { id: number; customer_name: string; amount: number; outstanding: number; due_date: string; days_overdue: number; status: string; note: string | null };
type Dialog = "invoice" | "bill" | "supplier" | null;
type BillRow = Bill & { amount_paid?: number };

const ACTION_COLOR = {
  stop_credit: "red", visit: "red", call: "amber", discount: "blue", send_reminder: "slate", wait: "green",
} as const;
const BUCKET_LABEL = { current: "Not due", "0-30": "1-30 days", "31-60": "31-60 days", "61-90": "61-90 days", "90+": "90+ days" };

export default function LedgerPage() {
  const [tab, setTab] = useState<"receivables" | "payables">("receivables");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [k, setK] = useState(0);
  const changed = () => setK((n) => n + 1);
  return (
    <>
      <PageHeader title="Ledger" subtitle="Who owes you, and who you owe"
        right={
          <div className="flex flex-wrap items-center gap-2">
            {tab === "receivables" ? (
              <Button onClick={() => setDialog("invoice")}><Plus className="size-4" /> Add invoice</Button>
            ) : (
              <>
                <Button variant="secondary" onClick={() => setDialog("supplier")}><Plus className="size-4" /> Add supplier</Button>
                <Button onClick={() => setDialog("bill")}><Plus className="size-4" /> Add bill</Button>
              </>
            )}
            <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5">
              {(["receivables", "payables"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${tab === t ? "bg-emerald-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>
                  {t === "receivables" ? "They owe me" : "I owe"}
                </button>
              ))}
            </div>
          </div>
        } />
      {tab === "receivables" ? <Receivables k={k} onChanged={changed} /> : <Payables k={k} onChanged={changed} />}
      {dialog === "invoice" && <AddInvoiceModal onClose={() => setDialog(null)} onSaved={changed} />}
      {dialog === "supplier" && <AddSupplierModal onClose={() => setDialog(null)} onSaved={changed} />}
      {dialog === "bill" && <AddBillModal onClose={() => setDialog(null)} onSaved={changed} />}
    </>
  );
}

function Receivables({ k, onChanged }: { k: number; onChanged: () => void }) {
  return (
    <>
      <OpenInvoices k={k} onChanged={onChanged} />
      <Ranking k={k} />
    </>
  );
}

function OpenInvoices({ k, onChanged }: { k: number; onChanged: () => void }) {
  const biz = useBusiness();
  const cur = biz?.currency ?? "USD";
  const { data, error, loading, reload } = useApi<OpenInvoice[]>(`/invoices?status=open&k=${k}`);
  const [paying, setPaying] = useState<OpenInvoice | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function markPaid(i: OpenInvoice) {
    if (!window.confirm(`Mark invoice #${i.id} from ${i.customer_name} as fully paid?`)) return;
    setErr(null);
    try { await api(`/invoices/${i.id}/paid`, { method: "PATCH" }); onChanged(); reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not update"); }
  }
  if (loading && !data) return <Loading />;
  if (error || !data) return <div className="mb-6"><ErrorBox message={error ?? "No data"} onRetry={reload} /></div>;
  return (
    <Card className="mb-6 overflow-x-auto p-0">
      <div className="px-5 pt-5"><CardTitle>Open invoices</CardTitle></div>
      {data.length === 0 ? (
        <p className="px-5 pb-5 text-sm text-slate-500">Nothing is owed to you right now. Use “Add invoice” when you sell on credit.</p>
      ) : (
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-y border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-5 py-2.5 font-medium">Customer</th>
              <th className="px-3 py-2.5 font-medium">Due</th>
              <th className="px-3 py-2.5 text-right font-medium">Invoice</th>
              <th className="px-3 py-2.5 text-right font-medium">Still owed</th>
              <th className="px-5 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((i) => (
              <tr key={i.id}>
                <td className="px-5 py-3"><p className="font-medium">{i.customer_name}</p><p className="text-xs text-slate-500">#{i.id}{i.note ? ` · ${i.note}` : ""}</p></td>
                <td className="px-3 py-3">{longDate(i.due_date)}{i.days_overdue > 0 && <span className="text-rose-600"> · {i.days_overdue}d overdue</span>}</td>
                <td className="px-3 py-3 text-right tabular">{money(i.amount, cur)}</td>
                <td className="px-3 py-3 text-right font-semibold tabular">{money(i.outstanding, cur)}{i.status === "partial" && <span className="ml-1 text-xs font-normal text-slate-500">part paid</span>}</td>
                <td className="px-5 py-3">
                  <div className="flex justify-end gap-1">
                    <Button variant="secondary" className="px-2.5" onClick={() => setPaying(i)}>Record payment</Button>
                    <Button variant="ghost" className="px-2.5" onClick={() => markPaid(i)}>Mark paid</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {err && <div className="m-4"><ErrorBox message={err} /></div>}
      {paying && <RecordPaymentModal invoice={paying} currency={cur} onClose={() => setPaying(null)} onSaved={() => { onChanged(); reload(); }} />}
    </Card>
  );
}

function Ranking({ k }: { k: number }) {
  const { data, error, loading, reload } = useApi<CollectionPriority>(`/collections/priority?k=${k}`);
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

function Payables({ k, onChanged }: { k: number; onChanged: () => void }) {
  const biz = useBusiness();
  const cur = biz?.currency ?? "USD";
  const { data, error, loading, reload } = useApi<BillRow[]>(`/bills?status=unpaid&k=${k}`);
  const [plan, setPlan] = useState<BillRow | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function markPaid(b: BillRow) {
    if (!window.confirm(`Mark the ${b.supplier_name} bill as paid? This records the money going out.`)) return;
    setErr(null);
    try { await api(`/bills/${b.id}/paid`, { method: "PATCH" }); onChanged(); reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not update"); }
  }
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;
  const owed = (b: BillRow) => b.amount - (b.amount_paid ?? 0);
  const total = data.reduce((sum, b) => sum + owed(b), 0);
  return (
    <>
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Stat label="Bills to pay" value={money(total, cur)} tone="warn" />
        <Stat label="Next due" value={data[0] ? longDate(data[0].due_date) : "—"} hint={data[0] ? `${data[0].supplier_name}, ${money(owed(data[0]), cur)}` : undefined} />
      </div>
      <Card className="overflow-x-auto p-0">
        {data.length === 0 ? (
          <p className="p-5 text-sm text-slate-500">No unpaid bills. Use “Add bill” when a supplier sends you one.</p>
        ) : (
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-5 py-3 font-medium">Supplier</th>
                <th className="px-3 py-3 font-medium">Due</th>
                <th className="px-3 py-3 font-medium">Note</th>
                <th className="px-3 py-3 text-right font-medium">Owed</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((b) => (
                <tr key={b.id}>
                  <td className="px-5 py-3 font-medium">{b.supplier_name}</td>
                  <td className="px-3 py-3">{longDate(b.due_date)}</td>
                  <td className="px-3 py-3 text-slate-500">{b.note ?? "—"}</td>
                  <td className="px-3 py-3 text-right font-semibold tabular">{money(owed(b), cur)}</td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-1">
                      <Button variant="secondary" className="px-2.5" onClick={() => setPlan(b)}>Make a plan</Button>
                      <Button variant="ghost" className="px-2.5" onClick={() => markPaid(b)}>Mark paid</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {err && <div className="mt-3"><ErrorBox message={err} /></div>}
      {plan && (
        <PlanModal bill={{ bill_id: plan.id, supplier: plan.supplier_name, outstanding: owed(plan), due_date: plan.due_date }}
          options={[]} currency={cur} onClose={() => setPlan(null)} onSaved={() => { onChanged(); reload(); }} />
      )}
      <p className="mt-3 text-xs text-slate-500">A plan only saves a draft. Review and approve it on the Supplier Plans page; nothing is paid or sent from here.</p>
    </>
  );
}
