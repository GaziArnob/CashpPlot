"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Bell, Sparkles } from "lucide-react";
import BalanceChart from "@/components/BalanceChart";
import { Badge, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { longDate, money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Dashboard } from "@/lib/types";

const BAND_TONE = { Excellent: "good", Good: "good", Fair: "warn", "Needs improvement": "bad" } as const;

export default function DashboardPage() {
  const { data, error, loading, reload } = useApi<Dashboard>("/dashboard/summary");
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;
  const cur = data.business.currency;

  return (
    <>
      <PageHeader title={data.business.name} subtitle={`Overview as of ${longDate(data.as_of)}`} />

      {data.cash_alert && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-5 py-4">
          <AlertTriangle className="size-5 text-rose-600" />
          <p className="flex-1 text-sm text-rose-900">
            <span className="font-semibold">Cash shortage ahead:</span> your balance may fall{" "}
            <span className="font-semibold">{money(data.cash_alert.gap, cur)}</span> below your safety threshold on{" "}
            <span className="font-semibold">{longDate(data.cash_alert.date)}</span>.
          </p>
          <Link href="/advisor" className="flex items-center gap-1 text-sm font-medium text-rose-700 hover:underline">
            See the plan <ArrowRight className="size-4" />
          </Link>
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Cash balance" value={money(data.balance, cur)} />
        <Stat label="Net this month" value={money(data.month_to_date.net, cur)}
          tone={data.month_to_date.net >= 0 ? "good" : "bad"}
          hint={`In ${money(data.month_to_date.income, cur)} · Out ${money(data.month_to_date.expense, cur)}`} />
        <Stat label="Overdue receivables" value={money(data.receivables.overdue, cur)} tone="warn"
          hint={`${data.receivables.customers_overdue} customers · ${money(data.receivables.outstanding, cur)} outstanding`} />
        <Stat label="Credit score" value={data.credit_score.score} tone={BAND_TONE[data.credit_score.band as keyof typeof BAND_TONE] ?? "default"}
          hint={data.credit_score.band} />
      </div>

      <Card className="mb-6 border-emerald-200 bg-gradient-to-br from-emerald-50 to-white">
        <div className="flex gap-3">
          <Sparkles className="mt-0.5 size-5 shrink-0 text-emerald-600" />
          <div>
            <p className="text-sm font-semibold text-emerald-900">Today&apos;s summary</p>
            <p className="mt-1 text-sm leading-relaxed text-slate-700">{data.summary}</p>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle right={<Link href="/cashflow" className="text-xs font-medium text-emerald-700 hover:underline">30-day view</Link>}>
            Projected balance, next 14 days
          </CardTitle>
          <BalanceChart data={data.forecast_preview} threshold={data.threshold} height={240} />
        </Card>

        <Card>
          <CardTitle right={<Link href="/ledger" className="text-xs font-medium text-emerald-700 hover:underline">Ledger</Link>}>
            Collect first
          </CardTitle>
          <ul className="divide-y divide-slate-100">
            {data.top_collections.map((c, i) => (
              <li key={c.customer_id} className="flex items-center gap-3 py-3">
                <span className="flex size-6 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium leading-snug">{c.customer_name}</p>
                  <p className="text-xs text-slate-500">
                    {c.max_days_overdue ? `${c.max_days_overdue} days overdue` : "Not yet due"}
                  </p>
                </div>
                <span className="text-sm font-semibold tabular">{money(c.overdue_amount, cur)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {data.notifications.length > 0 && (
        <Card className="mt-6">
          <CardTitle>Alerts</CardTitle>
          <ul className="space-y-2">
            {data.notifications.map((n) => (
              <li key={n.id} className="flex items-start gap-3 text-sm">
                <Bell className="mt-0.5 size-4 shrink-0 text-slate-400" />
                <span className="flex-1 text-slate-700">{n.message}</span>
                <Badge color={n.type === "cash_shortage" ? "red" : n.type === "overdue" ? "amber" : "slate"}>
                  {n.type.replace("_", " ")}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
