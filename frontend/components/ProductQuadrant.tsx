"use client";

import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import type { ProductClass } from "@/lib/types";

export type QuadrantProduct = {
  name: string; product_class: ProductClass; margin_pct: number | null; turnover: number | null; revenue_90d: number;
};

export const CLASS_META: Record<ProductClass, { label: string; color: string; badge: "green" | "blue" | "amber" | "red" | "slate" }> = {
  star: { label: "Star", color: "#8b72e0", badge: "green" },
  cash_cow: { label: "Cash cow", color: "#0284c7", badge: "blue" },
  slow: { label: "Slow mover", color: "#d97706", badge: "amber" },
  dead: { label: "Dead stock", color: "#f2817f", badge: "red" },
  new: { label: "New", color: "#908d98", badge: "slate" },
  inactive: { label: "Inactive", color: "#6e6b76", badge: "slate" },
};
export const QUADRANT_CLASSES: ProductClass[] = ["star", "cash_cow", "slow", "dead"];

export default function ProductQuadrant({ products, thresholds, height = 320 }: {
  products: QuadrantProduct[]; thresholds: { turnover_median: number; margin_median_pct: number }; height?: number;
}) {
  // Stock-outs report a very large turnover; cap the axis so the chart stays readable.
  const real = products.filter((p) => p.turnover !== null && p.turnover < 900).map((p) => p.turnover as number);
  const xMax = Math.ceil(Math.max(10, ...real) * 1.15);
  const points = (cls: ProductClass) => products
    .filter((p) => p.product_class === cls && p.turnover !== null && p.margin_pct !== null)
    .map((p) => ({ x: Math.min(p.turnover as number, xMax), y: p.margin_pct, z: Math.max(p.revenue_90d, 1), name: p.name }));
  const fastLine = thresholds.turnover_median * 0.6;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="#312e35" />
        <XAxis type="number" dataKey="x" domain={[0, xMax]} tick={{ fontSize: 11, fill: "#908d98" }}
          label={{ value: "Selling speed (stock turns a year) →", position: "insideBottom", offset: -4, fontSize: 11, fill: "#908d98" }} />
        <YAxis type="number" dataKey="y" unit="%" tick={{ fontSize: 11, fill: "#908d98" }} width={44}
          label={{ value: "Margin", angle: -90, position: "insideLeft", fontSize: 11, fill: "#908d98" }} />
        <ZAxis type="number" dataKey="z" range={[60, 400]} />
        <ReferenceLine x={fastLine} stroke="#6e6b76" strokeDasharray="4 4"
          label={{ value: "fast →", position: "insideTopRight", fontSize: 11, fill: "#908d98" }} />
        <ReferenceLine y={thresholds.margin_median_pct} stroke="#6e6b76" strokeDasharray="4 4"
          label={{ value: "median margin", position: "insideTopLeft", fontSize: 11, fill: "#908d98" }} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }}
          content={({ payload }) => {
            const p = payload?.[0]?.payload as { name: string; x: number; y: number } | undefined;
            if (!p) return null;
            return (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-sm">
                <p className="font-semibold">{p.name}</p>
                <p className="text-slate-500">{p.y}% margin · {p.x} turns/yr</p>
              </div>
            );
          }} />
        {QUADRANT_CLASSES.map((cls) => (
          <Scatter key={cls} name={CLASS_META[cls].label} data={points(cls)} fill={CLASS_META[cls].color}
            fillOpacity={0.75} isAnimationActive={false} />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
