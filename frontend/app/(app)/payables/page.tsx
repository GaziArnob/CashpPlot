"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, History, Info, Plus, ShieldCheck } from "lucide-react";
import BalanceChart from "@/components/BalanceChart";
import { DraftsSection, PlansSection } from "@/components/payables/PlansAndDrafts";
import PlanModal from "@/components/payables/PlanModal";
import { AddBillModal, AddSupplierModal } from "@/components/QuickAdd";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate, money, shortDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { BillOption, FinancingOption, PayablesAnalysis, RecHistoryItem, RecStep, UpcomingBill } from "@/lib/types";

const RISK = { low: "green", medium: "amber", high: "red" } as const;

function Step({ s, currency }: { s: RecStep; currency: string }) {
  const [open, setOpen] = useState(false);
  const title = s.type === "supplier_plan"
    ? `${s.kind === "partial" ? "Pay in parts" : "Ask for an extension"}: ${s.supplier}` : s.name;
  return (
    <li className="py-3">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-start gap-2 text-left">
        {open ? <ChevronDown className="mt-0.5 size-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 size-4 shrink-0 text-slate-400" />}
        <span className="flex-1">
          <span className="text-sm font-medium">{title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
            <Badge color={s.type === "financing" ? "amber" : "blue"}>{s.type === "financing" ? "financing (demo)" : "supplier"}</Badge>
            <Badge color={RISK[s.risk]}>{s.risk} risk</Badge>
            {s.needs_agreement && <Badge>needs supplier&apos;s agreement</Badge>}
            <span className="text-slate-500">lifts the lowest balance by {money(s.relief, currency)} · est. cost {money(s.cost, currency)}</span>
          </span>
        </span>
      </button>
      {open && <p className="mt-2 pl-6 text-sm leading-relaxed text-slate-600">{s.why}</p>}
    </li>
  );
}

function Recommendation({ a, onSaved }: { a: PayablesAnalysis; onSaved: () => void }) {
  const r = a.recommendation;
  const [busy, setBusy] = useState(false);
  const [showAlt, setShowAlt] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    setBusy(true);
    setError(null);
    try { await api("/payables/recommendations", { method: "POST" }); onSaved(); } catch (e) { setError(e instanceof Error ? e.message : "Could not save"); } finally { setBusy(false); }
  }
  return (
    <Card>
      <CardTitle right={<Button variant="secondary" onClick={save} disabled={busy}><History className="size-4" />{busy ? "Saving…" : "Save to history"}</Button>}>
        Recommendation
      </CardTitle>
      <p className="text-sm font-medium leading-relaxed">{r.headline}</p>
      {r.steps.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Lowest balance {money(r.lowest_balance_before ?? 0, a.currency)} → {money(r.lowest_balance_after ?? 0, a.currency)}
          {" "}· total estimated cost {money(r.total_cost, a.currency)}
          {r.remaining_gap > 0 && <span className="text-rose-600"> · {money(r.remaining_gap, a.currency)} still short</span>}
        </p>
      )}
      {r.steps.length > 0 && <ul className="mt-3 divide-y divide-slate-100">{r.steps.map((s, i) => <Step key={i} s={s} currency={a.currency} />)}</ul>}
      <ul className="mt-3 space-y-1.5 border-t border-slate-100 pt-3">
        {r.reasoning.map((t, i) => <li key={i} className="flex gap-2 text-xs text-slate-600"><Info className="mt-0.5 size-3.5 shrink-0 text-slate-400" />{t}</li>)}
      </ul>
      {r.alternatives.length > 0 && (
        <div className="mt-3">
          <button className="text-xs font-medium text-emerald-700 hover:underline" onClick={() => setShowAlt((v) => !v)}>
            {showAlt ? "Hide" : "Show"} {r.alternatives.length} options not chosen, and why
          </button>
          {showAlt && (
            <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
              {r.alternatives.map((s, i) => (
                <li key={i} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs">
                  <span className="font-medium">{s.type === "supplier_plan" ? `${s.kind.replace("_", " ")} · ${s.supplier}` : s.name}</span>
                  <span className="text-slate-500">cost {money(s.cost, a.currency)} · {s.why_not}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
    </Card>
  );
}

function Financing({ options, currency, title, hint }: { options: FinancingOption[]; currency: string; title: string; hint?: string }) {
  return (
    <Card className="overflow-x-auto p-0">
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-5">
        <CardTitle>{title}</CardTitle>
        <Badge color="amber">DEMO offers, not real offers or approvals</Badge>
      </div>
      {hint && <p className="px-5 pb-2 text-xs text-slate-500">{hint}</p>}
      {options.length === 0 ? <p className="px-5 pb-5 text-sm text-slate-500">No financing is needed right now.</p> : (
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr className="border-y border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-5 py-2.5 font-medium">Offer</th>
              <th className="px-3 py-2.5 text-right font-medium">Principal</th>
              <th className="px-3 py-2.5 text-right font-medium">Fees</th>
              <th className="px-3 py-2.5 text-right font-medium">Interest</th>
              <th className="px-3 py-2.5 text-right font-medium">Total repayment</th>
              <th className="px-3 py-2.5 text-right font-medium">Total cost</th>
              <th className="px-5 py-2.5 font-medium">Repayment dates</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {options.map((f) => (
              <tr key={f.offer_id} className="align-top">
                <td className="px-5 py-3">
                  <p className="font-medium">{f.name}</p>
                  <p className="text-xs text-slate-500">{f.provider}</p>
                  <p className="mt-1 flex flex-wrap gap-1">
                    {f.meets_deadline ? <Badge color="green">funds by {shortDate(f.funds_available)}</Badge> : <Badge color="red">too slow ({shortDate(f.funds_available)})</Badge>}
                    <Badge color={RISK[f.risk]}>{f.risk} risk</Badge>
                  </p>
                </td>
                <td className="px-3 py-3 text-right tabular">{money(f.principal, currency)}</td>
                <td className="px-3 py-3 text-right tabular">{money(f.fees, currency)}</td>
                <td className="px-3 py-3 text-right tabular">{money(f.interest, currency)}</td>
                <td className="px-3 py-3 text-right font-medium tabular">{money(f.total_repayment, currency)}</td>
                <td className="px-3 py-3 text-right tabular">
                  <p className="font-semibold">{money(f.total_cost, currency)}</p>
                  <p className="text-xs text-slate-500">{f.effective_annual_rate_pct}% a year</p>
                </td>
                <td className="px-5 py-3 text-xs text-slate-600">
                  {f.repayments.map((r, i) => <p key={i}>{shortDate(r.date)}: {money(r.amount, currency)}</p>)}
                  <p className="mt-1 text-slate-400">from {f.repaid_from}</p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function Upcoming({ a, onPlan }: { a: PayablesAnalysis; onPlan: (b: UpcomingBill) => void }) {
  const cur = a.currency;
  const confirmed = a.cashflow.outflows.filter((o) => o.basis === "confirmed");
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <Card>
        <CardTitle right={<Badge color="blue">confirmed</Badge>}>Upcoming payments</CardTitle>
        {a.upcoming_bills.length === 0 ? <p className="text-sm text-slate-500">No unpaid supplier bills. Press “Add bill” above, then make a payment plan for it here.</p> : (
          <ul className="divide-y divide-slate-100">
            {a.upcoming_bills.map((b) => (
              <li key={b.bill_id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{b.supplier}</p>
                  <p className="text-xs text-slate-500">
                    due {longDate(b.due_date)}{b.overdue && <span className="text-rose-600"> · overdue</span>}
                    {b.plan_id && <span className="text-emerald-700"> · on a plan</span>}
                  </p>
                </div>
                <span className="text-sm font-semibold tabular">{money(b.outstanding, cur)}</span>
                {!b.plan_id && <Button variant="secondary" onClick={() => onPlan(b)}>Plan</Button>}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-slate-500">
          {confirmed.length} confirmed payments (bills, installments, rent, salaries) in the next 30 days. Rent, salaries and loan
          installments are fixed; supplier bills can be rescheduled.
        </p>
      </Card>
      <Card>
        <CardTitle right={<Badge color="amber">estimates</Badge>}>Money expected from customers</CardTitle>
        {a.cashflow.receipts.length === 0 ? <p className="text-sm text-slate-500">No open invoices.</p> : (
          <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
            {a.cashflow.receipts.map((r) => (
              <li key={r.invoice_id} className="py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{r.customer}</span>
                  <span className="text-sm tabular">{money(r.counted, cur)}{r.weight < 1 && <span className="text-xs text-slate-400"> of {money(r.outstanding, cur)}</span>}</span>
                </div>
                <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                  expected {shortDate(r.expected_date)} · {r.basis}
                  {r.at_risk && <Badge color="red">at risk</Badge>}
                  {!r.in_window && <Badge>after 30 days</Badge>}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function History_({ onOpen }: { onOpen?: () => void }) {
  const [open, setOpen] = useState(false);
  const h = useApi<RecHistoryItem[]>(open ? "/payables/recommendations" : null);
  return (
    <Card>
      <button onClick={() => { setOpen((v) => !v); onOpen?.(); }} className="flex w-full items-center justify-between text-left">
        <span className="text-sm font-semibold text-slate-700">Recommendation history</span>
        {open ? <ChevronDown className="size-4 text-slate-400" /> : <ChevronRight className="size-4 text-slate-400" />}
      </button>
      {open && (h.loading && !h.data ? <Loading /> : h.data && h.data.length > 0 ? (
        <ul className="mt-3 divide-y divide-slate-100">
          {h.data.map((x) => (
            <li key={x.id} className="py-2.5 text-sm">
              <p className="text-xs text-slate-500">{new Date(x.created_at + "Z").toLocaleString()} · cost {money(x.total_cost)}</p>
              <p>{x.headline}</p>
            </li>
          ))}
        </ul>
      ) : <p className="mt-3 text-sm text-slate-500">Nothing saved yet. Use “Save to history” on a recommendation.</p>)}
    </Card>
  );
}

export default function PayablesPage() {
  const analysis = useApi<PayablesAnalysis>("/payables/analysis");
  const [planFor, setPlanFor] = useState<UpcomingBill | null>(null);
  const [adding, setAdding] = useState<"supplier" | "bill" | null>(null);
  const [draftKey, setDraftKey] = useState(0);
  const [historyKey, setHistoryKey] = useState(0);
  const [amount, setAmount] = useState("");
  const [custom, setCustom] = useState<FinancingOption[] | null>(null);
  const [customError, setCustomError] = useState<string | null>(null);

  const a = analysis.data;
  if (analysis.loading && !a) return <><PageHeader title="Supplier Payments & Financing" /><Loading label="Checking your payment dates" /></>;
  if (analysis.error || !a) return <ErrorBox message={analysis.error ?? "No data"} onRetry={analysis.reload} />;

  const cur = a.currency;
  const options = new Map<number, BillOption[]>(a.bill_options.map((o) => [o[0].bill_id, o]));
  const chart = a.cashflow.series.map((r) => ({ date: r.date, balance: r.balance, status: r.below_threshold ? "shortage" : "ok" }));
  const worst = a.conflicts.length ? a.conflicts.reduce((m, c) => (c.worst_gap > m.worst_gap ? c : m)) : null;
  const onChanged = () => { analysis.reload(); setDraftKey((k) => k + 1); };

  async function compare() {
    setCustomError(null);
    try {
      const r = await api<{ options: FinancingOption[] }>(`/financing/compare?amount=${Number(amount)}&needed_by_days=7&duration_days=30`);
      setCustom(r.options);
    } catch (e) { setCustomError(e instanceof Error ? e.message : "Could not compare"); }
  }

  return (
    <>
      <PageHeader title="Supplier Payments & Financing"
        subtitle="Spot payment clashes early, plan with your suppliers, and compare the cost of financing"
        right={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setAdding("supplier")}><Plus className="size-4" /> Add supplier</Button>
            <Button onClick={() => setAdding("bill")}><Plus className="size-4" /> Add bill</Button>
          </div>
        } />

      <div className="mb-6 flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 px-5 py-3 text-sm text-sky-900">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" />
        <span>You stay in control. This page never pays a supplier, never sends a message and never applies for a loan.
          Plans need your approval, and a plan only changes your forecast after the supplier agrees. Financing figures are DEMO offers.</span>
      </div>

      {worst ? (
        <Card className="mb-6 border-rose-200 bg-rose-50">
          <div className="flex gap-3">
            <AlertTriangle className="mt-0.5 size-5 shrink-0 text-rose-600" />
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-rose-700">Payment clash predicted</p>
              <p className="mt-1 text-2xl font-semibold text-rose-700 tabular">{money(worst.worst_gap, cur)} short</p>
              <p className="mt-1 text-sm text-rose-900">{worst.explanation}</p>
            </div>
          </div>
        </Card>
      ) : (
        <Card className="mb-6 border-emerald-200 bg-emerald-50">
          <div className="flex gap-3"><CheckCircle2 className="mt-0.5 size-5 text-emerald-600" />
            <p className="text-sm text-emerald-900">No payment clash in the next 30 days. Cash stays above your safety level.</p></div>
        </Card>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Cash today" value={money(a.cashflow.start_balance, cur)} hint={`Safety level ${money(a.cashflow.threshold, cur)}`} />
        <Stat label="Bills to pay (30d)" value={money(a.upcoming_bills.reduce((s, b) => s + b.outstanding, 0), cur)} tone="warn" hint={`${a.upcoming_bills.length} supplier bills`} />
        <Stat label="At-risk invoices" value={a.at_risk_invoices.length} tone={a.at_risk_invoices.length ? "bad" : "good"}
          hint={`${money(a.at_risk_invoices.reduce((s, r) => s + r.outstanding, 0), cur)} later than usual`} />
        <Stat label="Days below safety level" value={a.cashflow.series.filter((r) => r.below_threshold).length}
          tone={a.conflicts.length ? "bad" : "good"} />
      </div>

      <Card className="mb-6">
        <CardTitle right={<span className="text-xs text-slate-500">Red dots: below your safety level</span>}>30-day cash flow</CardTitle>
        <BalanceChart data={chart} threshold={a.cashflow.threshold} height={280} />
        <p className="mt-2 text-xs text-slate-500">
          Confirmed: supplier bills, installments, rent, salaries, loan payments. Estimated: day-to-day sales and costs, and
          customer payments on their expected dates. Each amount is counted once.
        </p>
      </Card>

      <div className="mb-6"><Upcoming a={a} onPlan={setPlanFor} /></div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Recommendation a={a} onSaved={() => setHistoryKey((k) => k + 1)} />
        <div className="space-y-6">
          <PlansSection bills={a.upcoming_bills} optionsByBill={options} currency={cur} onChanged={onChanged} refreshKey={draftKey} />
        </div>
      </div>

      <div className="mb-6"><DraftsSection refreshKey={draftKey} /></div>

      <div className="mb-6 space-y-4">
        <Financing options={a.financing} currency={cur} title="Financing comparison for your shortfall"
          hint="Sized to the shortfall above. Costs are estimates from demo rates." />
        <Card>
          <CardTitle>Compare for a different amount</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))} inputMode="decimal"
              placeholder={`Amount in ${cur}`} className="w-48 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <Button onClick={compare} disabled={!Number(amount)}>Compare</Button>
          </div>
          {customError && <div className="mt-3"><ErrorBox message={customError} /></div>}
        </Card>
        {custom && <Financing options={custom} currency={cur} title={`Comparison for ${money(Number(amount), cur)}`} />}
      </div>

      <History_ key={historyKey} />

      {adding === "supplier" && <AddSupplierModal onClose={() => setAdding(null)} onSaved={onChanged} />}
      {adding === "bill" && <AddBillModal onClose={() => setAdding(null)} onSaved={onChanged} />}
      {planFor && (
        <PlanModal bill={planFor} options={options.get(planFor.bill_id) ?? []} currency={cur}
          onClose={() => setPlanFor(null)} onSaved={onChanged} />
      )}
    </>
  );
}
