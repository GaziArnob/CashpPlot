"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Info } from "lucide-react";
import BalanceChart from "@/components/BalanceChart";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { LoanOption, LoanReadiness, WhatIf } from "@/lib/types";

export default function LoanPage() {
  const readiness = useApi<LoanReadiness>("/loan/readiness");
  const recs = useApi<{ options: LoanOption[] }>("/loan/recommendations");
  if (readiness.loading && !readiness.data) return <Loading />;
  if (readiness.error || !readiness.data) return <ErrorBox message={readiness.error ?? "No data"} onRetry={readiness.reload} />;
  const r = readiness.data;

  return (
    <>
      <PageHeader title="Loan Center" subtitle="How much you can safely borrow, and from whom" />
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 px-5 py-3 text-sm text-sky-900">
        <Info className="mt-0.5 size-4 shrink-0" /> {r.disclaimer}
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Loan readiness" value={r.ready ? "Ready" : "Not yet"} tone={r.ready ? "good" : "warn"}
          hint={`Credit score ${r.score} (${r.band})`} />
        <Stat label="Safe monthly installment" value={money(r.safe_monthly_installment)}
          hint={`${Math.round(r.capacity.alpha * 100)}% of a weak month's cash flow, minus ${money(r.capacity.existing_emi)} existing`} />
        <Stat label="Up to" value={money(r.max_recommended_amount)} tone="good" hint="Largest matching offer" />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="overflow-x-auto p-0 xl:col-span-2">
          <div className="px-5 pt-5"><CardTitle>Matching financing options (lowest cost first)</CardTitle></div>
          {recs.loading && !recs.data ? <Loading /> : (
            <table className="w-full min-w-[600px] text-sm">
              <thead>
                <tr className="border-y border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-2.5 font-medium">Product</th>
                  <th className="px-3 py-2.5 text-right font-medium">Amount</th>
                  <th className="px-3 py-2.5 text-right font-medium">Rate</th>
                  <th className="px-3 py-2.5 text-right font-medium">Monthly</th>
                  <th className="px-5 py-2.5 text-right font-medium">Total interest</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(recs.data?.options ?? []).map((o, i) => (
                  <tr key={o.product_id}>
                    <td className="px-5 py-3">
                      <p className="font-medium">{o.name} {i === 0 && <Badge color="green">lowest cost</Badge>}</p>
                      <p className="text-xs text-slate-500">{o.lender} · {o.tenure_months} months</p>
                    </td>
                    <td className="px-3 py-3 text-right font-semibold tabular">{money(o.recommended_amount)}</td>
                    <td className="px-3 py-3 text-right tabular">{o.rate}%</td>
                    <td className="px-3 py-3 text-right tabular">{money(o.monthly_installment)}</td>
                    <td className="px-5 py-3 text-right tabular">{money(o.total_interest)}</td>
                  </tr>
                ))}
                {recs.data && recs.data.options.length === 0 && (
                  <tr><td colSpan={5} className="px-5 py-6 text-center text-slate-500">No product fits safely yet. Work through the checklist first.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </Card>

        <Card>
          <CardTitle>Readiness checklist</CardTitle>
          <ul className="space-y-3">
            {r.checklist.map((c) => (
              <li key={c.item} className="flex gap-3">
                {c.done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <Circle className="mt-0.5 size-4 shrink-0 text-slate-300" />}
                <div>
                  <p className={`text-sm ${c.done ? "text-slate-700" : "font-medium"}`}>{c.item}</p>
                  <p className="text-xs text-slate-500">{c.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <WhatIfSimulator />
    </>
  );
}

function Slider({ label, value, onChange, min, max, step, format }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; format: (v: number) => string;
}) {
  return (
    <label className="block">
      <div className="mb-1 flex justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-medium tabular">{format(value)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-emerald-600" />
    </label>
  );
}

function simulate(sales: number, expense: number, loan: number, tenure: number) {
  return api<WhatIf>("/loan/what-if", {
    method: "POST",
    body: JSON.stringify({ days: 30, sales_change_pct: sales, extra_monthly_expense: expense, loan_amount: loan, loan_tenure_months: tenure }),
  });
}

function WhatIfSimulator() {
  const [sales, setSales] = useState(0);
  const [expense, setExpense] = useState(0);
  const [loan, setLoan] = useState(50000);
  const [tenure, setTenure] = useState(12);
  const [result, setResult] = useState<WhatIf | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await simulate(sales, expense, loan, tenure));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // First run with the default inputs.
    simulate(0, 0, 50000, 12).then(setResult).catch((e) => setError(e instanceof Error ? e.message : "Simulation failed"));
  }, []);

  const merged = result?.base.series.map((p, i) => ({ ...p, scenario: result.scenario.series[i]?.balance }));

  return (
    <Card>
      <CardTitle>What-if simulator: next 30 days</CardTitle>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-5">
          <Slider label="Sales change" value={sales} onChange={setSales} min={-30} max={30} step={5} format={(v) => `${v > 0 ? "+" : ""}${v}%`} />
          <Slider label="New monthly expense" value={expense} onChange={setExpense} min={0} max={50000} step={5000} format={(v) => money(v)} />
          <Slider label="New loan received now" value={loan} onChange={setLoan} min={0} max={300000} step={10000} format={(v) => money(v)} />
          <Slider label="Loan tenure" value={tenure} onChange={setTenure} min={3} max={36} step={3} format={(v) => `${v} months`} />
          <Button onClick={run} disabled={busy} className="w-full">{busy ? "Simulating…" : "Run simulation"}</Button>
          {error && <ErrorBox message={error} />}
        </div>
        <div className="lg:col-span-2">
          {result && merged ? (
            <>
              <div className="mb-3 flex flex-wrap gap-4 text-xs">
                <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-emerald-600" />Today&apos;s plan</span>
                <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 border-t-2 border-dashed border-indigo-500" />Scenario</span>
              </div>
              <BalanceChart data={merged} threshold={result.threshold} height={260} scenarioLabel="Scenario" />
              <div className="mt-4 grid grid-cols-3 gap-3 text-center">
                <Mini label="Shortage days" base={result.base.shortage_days} scenario={result.scenario.shortage_days} better="lower" />
                <Mini label="Lowest balance" base={result.base.min_balance.balance} scenario={result.scenario.min_balance.balance} money />
                <Mini label="Balance in 30 days" base={result.base.end_balance} scenario={result.scenario.end_balance} money />
              </div>
              {result.inputs.new_monthly_installment > 0 && (
                <p className="mt-3 text-xs text-slate-500">Includes a new installment of {money(result.inputs.new_monthly_installment)} a month.</p>
              )}
            </>
          ) : <Loading label="Simulating" />}
        </div>
      </div>
    </Card>
  );
}

function Mini({ label, base, scenario, money: isMoney, better = "higher" }: {
  label: string; base: number; scenario: number; money?: boolean; better?: "higher" | "lower";
}) {
  const fmt = (v: number) => (isMoney ? money(v) : String(v));
  const improved = better === "higher" ? scenario > base : scenario < base;
  const same = scenario === base;
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-sm font-semibold tabular ${same ? "text-slate-700" : improved ? "text-emerald-700" : "text-rose-600"}`}>{fmt(scenario)}</p>
      <p className="text-xs text-slate-400 tabular">was {fmt(base)}</p>
    </div>
  );
}
