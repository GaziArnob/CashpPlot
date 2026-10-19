"use client";

import { Boxes, Plus, ShoppingCart } from "lucide-react";
import { useState } from "react";
import { AddProductModal, SaleModal, StockModal } from "@/components/QuickAdd";
import ProductQuadrant, { CLASS_META, QUADRANT_CLASSES } from "@/components/ProductQuadrant";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ProductPerf, ProductPerformance } from "@/lib/types";

function Row({ p, onSell, onStock }: { p: ProductPerf; onSell: () => void; onStock: () => void }) {
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
      <td className="px-3 py-3 text-right tabular">
        {p.cash_impact === 0 ? <span className="text-slate-400">—</span> : (
          <span className={p.cash_impact > 0 ? "text-emerald-700" : "text-rose-600"}>
            {p.cash_impact > 0 ? "+" : "−"}{money(Math.abs(p.cash_impact))}
          </span>
        )}
      </td>
      <td className="px-5 py-3">
        <div className="flex justify-end gap-1">
          <Button variant="secondary" className="px-2.5" onClick={onSell}>Sell</Button>
          <Button variant="ghost" className="px-2.5" onClick={onStock}>Stock</Button>
        </div>
      </td>
    </tr>
  );
}

export default function ProductsPage() {
  const { data, error, loading, reload } = useApi<ProductPerformance>("/products/performance");
  const [dialog, setDialog] = useState<{ kind: "product" | "sale" | "stock"; product?: number } | null>(null);
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;

  return (
    <>
      <PageHeader title="Products" subtitle="Which products to push, keep, shrink or clear, within the cash you have"
        right={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setDialog({ kind: "stock" })}><Boxes className="size-4" /> Stock</Button>
            <Button variant="secondary" onClick={() => setDialog({ kind: "sale" })}><ShoppingCart className="size-4" /> Record sale</Button>
            <Button onClick={() => setDialog({ kind: "product" })}><Plus className="size-4" /> Add product</Button>
          </div>
        } />
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
        <table className="w-full min-w-[1040px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-5 py-3 font-medium">Product</th>
              <th className="px-3 py-3 text-right font-medium">Revenue 30d</th>
              <th className="px-3 py-3 text-right font-medium">Margin</th>
              <th className="px-3 py-3 text-right font-medium">Stock</th>
              <th className="px-3 py-3 text-right font-medium">Cash back in</th>
              <th className="px-3 py-3 font-medium">Recommendation</th>
              <th className="px-3 py-3 text-right font-medium">Cash impact</th>
              <th className="px-5 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.products.map((p) => <Row key={p.product_id} p={p} onSell={() => setDialog({ kind: "sale", product: p.product_id })} onStock={() => setDialog({ kind: "stock", product: p.product_id })} />)}
            {data.products.length === 0 && <tr><td colSpan={8} className="px-5 py-10 text-center text-slate-500">No products yet. Press “Add product” to start, then record sales and stock as they happen.</td></tr>}
          </tbody>
        </table>
      </Card>
      {dialog?.kind === "product" && <AddProductModal onClose={() => setDialog(null)} onSaved={reload} />}
      {dialog?.kind === "sale" && <SaleModal product={dialog.product} onClose={() => setDialog(null)} onSaved={reload} />}
      {dialog?.kind === "stock" && <StockModal product={dialog.product} onClose={() => setDialog(null)} onSaved={reload} />}
      <p className="mt-3 text-xs text-slate-500">
        Fast = stock turns at least 60% of the median ({data.thresholds.turnover_median}/yr); slow = under 25%.
        High margin = at or above the median ({data.thresholds.margin_median_pct}%). Dead = stock but no sale in 60 days.
      </p>
    </>
  );
}
