"use client";

import ProductQuadrant, { CLASS_META, QUADRANT_CLASSES } from "@/components/ProductQuadrant";
import { Badge, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ProductPerf, ProductPerformance } from "@/lib/types";

function Row({ p }: { p: ProductPerf }) {
  const meta = CLASS_META[p.product_class];
  return (
    <tr className="align-top hover:bg-slate-50">
      <td className="px-5 py-3">
        <p className="font-medium">{p.name}</p>
        <Badge color={meta.badge}>{meta.label}</Badge>
      </td>
      <td className="px-3 py-3 text-right tabular">
        <p>{money(p.revenue_30d)}</p>
        {p.growth_pct !== null && (
          <p className={`text-xs ${p.growth_pct >= 0 ? "text-emerald-700" : "text-rose-600"}`}>
            {p.growth_pct >= 0 ? "+" : ""}{p.growth_pct}% vs prior 30d
          </p>
        )}
      </td>
      <td className="px-3 py-3 text-right tabular">
        <p>{p.margin_pct ?? "—"}%</p>
        <p className="text-xs text-slate-500">{p.profit_share_pct}% of profit</p>
      </td>
      <td className="px-3 py-3 text-right tabular">
        <p>{p.stock_qty.toLocaleString()} units</p>
        <p className="text-xs text-slate-500">{p.days_of_stock !== null ? `${Math.round(p.days_of_stock)} days left` : "no recent sales"}</p>
      </td>
      <td className="px-3 py-3 text-right tabular">
        {p.cash_conversion_days !== null ? `${p.cash_conversion_days} d` : "—"}
        {p.cash_share_pct !== null && <p className="text-xs text-slate-500">{p.cash_share_pct}% cash sales</p>}
      </td>
      <td className="px-3 py-3 text-sm text-slate-700">{p.action}</td>
      <td className="px-5 py-3 text-right tabular">
        {p.cash_impact === 0 ? <span className="text-slate-400">—</span> : (
          <span className={p.cash_impact > 0 ? "text-emerald-700" : "text-rose-600"}>
            {p.cash_impact > 0 ? "+" : "−"}{money(Math.abs(p.cash_impact))}
          </span>
        )}
      </td>
    </tr>
  );
}

export default function ProductsPage() {
  const { data, error, loading, reload } = useApi<ProductPerformance>("/products/performance");
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;

  return (
    <>
      <PageHeader title="Products" subtitle="Which products to push, keep, shrink or clear, within the cash you have" />
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Cash stuck in slow & dead stock" value={money(data.cash_tied_in_slow_and_dead)} tone="warn" />
        <Stat label="Cash freed by clearing" value={money(data.cash_freed_if_cleared)} tone="good"
          hint="At the suggested discounts" />
        <Stat label="Budget to scale up stars" value={money(data.cash_budget)} tone={data.cash_budget ? "good" : "bad"}
          hint={data.cash_budget ? `Stars want ${money(data.scale_up_wanted)}` : "None: a cash gap is coming, scale up waits"} />
        <Stat label="Product mix" value={`${data.counts.star} ★ · ${data.counts.dead} dead`}
          hint={`${data.counts.cash_cow} cash cows · ${data.counts.slow} slow · ${data.counts.new} new`} />
      </div>

      <Card className="mb-6">
        <CardTitle right={
          <div className="flex flex-wrap gap-3 text-xs">
            {QUADRANT_CLASSES.map((c) => (
              <span key={c} className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full" style={{ background: CLASS_META[c].color }} />{CLASS_META[c].label}
              </span>
            ))}
          </div>
        }>Product quadrant (bubble size = 90-day revenue)</CardTitle>
        <ProductQuadrant products={data.products} thresholds={data.thresholds} />
      </Card>

      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[960px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-5 py-3 font-medium">Product</th>
              <th className="px-3 py-3 text-right font-medium">Revenue 30d</th>
              <th className="px-3 py-3 text-right font-medium">Margin</th>
              <th className="px-3 py-3 text-right font-medium">Stock</th>
              <th className="px-3 py-3 text-right font-medium">Cash back in</th>
              <th className="px-3 py-3 font-medium">Recommendation</th>
              <th className="px-5 py-3 text-right font-medium">Cash impact</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.products.map((p) => <Row key={p.product_id} p={p} />)}
          </tbody>
        </table>
      </Card>
      <p className="mt-3 text-xs text-slate-500">
        Fast = stock turns at least 60% of the median ({data.thresholds.turnover_median}/yr); slow = under 25%.
        High margin = at or above the median ({data.thresholds.margin_median_pct}%). Dead = stock but no sale in 60 days.
      </p>
    </>
  );
}
