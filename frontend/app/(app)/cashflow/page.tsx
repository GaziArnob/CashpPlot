"use client";

import { useState } from "react";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import BalanceChart from "@/components/BalanceChart";
import { Badge, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { longDate, money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Forecast } from "@/lib/types";

type CalendarDay = {
  date: string; projected_balance: number; status: string;
  inflows: { what: string; amount: number; probability: number }[];
  outflows: { what: string; amount: number; overdue: boolean }[];
};

const METHOD = { holt_winters: "Holt-Winters (weekly seasonality)", weighted_moving_average: "Weighted moving average", average: "Simple average" };

export default function CashFlowPage() {
  const [days, setDays] = useState(30);
  const fc = useApi<Forecast>(`/cashflow/forecast?days=${days}`);
  const cal = useApi<{ days: CalendarDay[] }>(`/cashflow/calendar?days=${days}`);

  const picker = (
    <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5">
      {[7, 15, 30].map((d) => (
        <button key={d} onClick={() => setDays(d)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${days === d ? "bg-emerald-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>
          {d} days
        </button>
      ))}
    </div>
  );

  if (fc.loading && !fc.data) return <><PageHeader title="Cash Flow Forecast" right={picker} /><Loading /></>;
  if (fc.error || !fc.data) return <ErrorBox message={fc.error ?? "No data"} onRetry={fc.reload} />;
  const f = fc.data;

  return (
    <>
      <PageHeader title="Cash Flow Forecast"
        subtitle={`Projected daily balance from ${f.history_days} days of history · ${METHOD[f.method as keyof typeof METHOD] ?? f.method}`}
        right={picker} />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Balance today" value={money(f.start_balance)} hint={`Safety threshold ${money(f.threshold)}`} />
        <Stat label="Lowest balance" value={money(f.min_balance.balance)} tone={f.min_balance.balance < f.threshold ? "bad" : "good"}
          hint={longDate(f.min_balance.date)} />
        <Stat label="Shortage days" value={f.shortages.length} tone={f.shortages.length ? "bad" : "good"}
          hint={f.first_shortage ? `First on ${longDate(f.first_shortage.date)}` : "None expected"} />
        <Stat label="Largest gap" value={money(f.largest_gap)} tone={f.largest_gap ? "bad" : "default"}
          hint={`${f.at_risk_days} more days at risk`} />
      </div>

      <Card className="mb-6">
        <CardTitle right={<span className="text-xs text-slate-500">Shaded: 80% range · Red dots: below threshold</span>}>
          Projected balance
        </CardTitle>
        <BalanceChart data={f.series} threshold={f.threshold} showBand height={320} />
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardTitle>Why the shortage happens</CardTitle>
          {f.drivers.length === 0 ? (
            <p className="text-sm text-slate-500">No shortage in this period.</p>
          ) : (
            <ul className="space-y-3">
              {f.drivers.map((d, i) => (
                <li key={i} className="flex items-center justify-between gap-3 text-sm">
                  <div>
                    <p className="font-medium">{d.kind === "bill" ? `Bill to ${d.supplier}` : "Loan installment"}</p>
                    <p className="text-xs text-slate-500">Due {longDate(d.date)}</p>
                  </div>
                  <span className="font-semibold text-rose-600 tabular">−{money(d.amount)}</span>
                </li>
              ))}
              {f.overdue_receivables > 0 && (
                <li className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">
                  {money(f.overdue_receivables)} in overdue invoices is not counted as coming in. Collecting it can close the gap.
                </li>
              )}
            </ul>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <CardTitle>Known money in and out</CardTitle>
          {cal.loading && !cal.data ? <Loading /> : (
            <div className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
              {(cal.data?.days ?? []).map((d) => (
                <div key={d.date} className="py-3">
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-sm font-medium">{longDate(d.date)}</span>
                    <span className="flex items-center gap-2 text-xs text-slate-500">
                      Balance after <span className="font-semibold text-slate-700 tabular">{money(d.projected_balance)}</span>
                      {d.status === "shortage" && <Badge color="red">shortage</Badge>}
                      {d.status === "at_risk" && <Badge color="amber">at risk</Badge>}
                    </span>
                  </div>
                  {d.inflows.map((x, i) => (
                    <div key={`i${i}`} className="flex items-center justify-between py-0.5 text-sm">
                      <span className="flex items-center gap-2 text-slate-600">
                        <ArrowDownLeft className="size-3.5 text-emerald-600" />{x.what}
                        <span className="text-xs text-slate-400">({Math.round(x.probability * 100)}% likely on time)</span>
                      </span>
                      <span className="text-emerald-700 tabular">+{money(x.amount)}</span>
                    </div>
                  ))}
                  {d.outflows.map((x, i) => (
                    <div key={`o${i}`} className="flex items-center justify-between py-0.5 text-sm">
                      <span className="flex items-center gap-2 text-slate-600">
                        <ArrowUpRight className="size-3.5 text-rose-600" />{x.what}
                      </span>
                      <span className="text-rose-600 tabular">−{money(x.amount)}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
