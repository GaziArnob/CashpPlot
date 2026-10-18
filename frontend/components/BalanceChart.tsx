"use client";

import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { compact, money, shortDate } from "@/lib/format";

type Point = { date: string; balance: number; low?: number; high?: number; status?: string; scenario?: number };

export default function BalanceChart({ data, threshold, height = 280, showBand = false, scenarioLabel }: {
  data: Point[]; threshold: number; height?: number; showBand?: boolean; scenarioLabel?: string;
}) {
  const rows = data.map((d) => ({ ...d, band: d.low !== undefined ? [d.low, d.high] : undefined }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: "#64748b" }}
          tickLine={false} axisLine={{ stroke: "#cbd5e1" }} minTickGap={24} />
        <YAxis tickFormatter={compact} tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={false} width={44} />
        <Tooltip
          formatter={(v, name) => {
            if (Array.isArray(v)) return [`${money(v[0] as number)} to ${money(v[1] as number)}`, "80% range"];
            return [money(v as number), name === "scenario" ? (scenarioLabel ?? "Scenario") : "Balance"];
          }}
          labelFormatter={(l) => shortDate(String(l))}
          contentStyle={{ borderRadius: 8, borderColor: "#e2e8f0", fontSize: 12 }}
        />
        {showBand && <Area dataKey="band" stroke="none" fill="#10b981" fillOpacity={0.1} isAnimationActive={false} />}
        <ReferenceLine y={threshold} stroke="#f43f5e" strokeDasharray="4 4"
          label={{ value: `Threshold ${compact(threshold)}`, position: "insideTopLeft", fill: "#e11d48", fontSize: 11 }} />
        <ReferenceLine y={0} stroke="#94a3b8" />
        <Line dataKey="balance" stroke="#059669" strokeWidth={2} isAnimationActive={false}
          dot={(p) => {
            const { cx, cy, payload, index } = p as { cx: number; cy: number; payload: Point; index: number };
            if (payload.status !== "shortage" && !(payload.balance < threshold)) return <g key={index} />;
            return <circle key={index} cx={cx} cy={cy} r={3.5} fill="#e11d48" stroke="white" strokeWidth={1} />;
          }} />
        {data.some((d) => d.scenario !== undefined) && (
          <Line dataKey="scenario" stroke="#6366f1" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
