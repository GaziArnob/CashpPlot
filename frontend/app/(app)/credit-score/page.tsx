"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardTitle, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { shortDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Credit } from "@/lib/types";

const BANDS = [
  { from: 300, to: 550, color: "#f43f5e", label: "Needs improvement" },
  { from: 550, to: 650, color: "#f59e0b", label: "Fair" },
  { from: 650, to: 750, color: "#10b981", label: "Good" },
  { from: 750, to: 900, color: "#059669", label: "Excellent" },
];

function polar(score: number, r: number) {
  const angle = Math.PI * (1 - (score - 300) / 600);
  return [120 + r * Math.cos(angle), 120 - r * Math.sin(angle)];
}

function Gauge({ score, band }: { score: number; band: string }) {
  const arc = (from: number, to: number) => {
    const [x1, y1] = polar(from, 96);
    const [x2, y2] = polar(to, 96);
    return `M${x1} ${y1} A96 96 0 0 1 ${x2} ${y2}`;
  };
  const [nx, ny] = polar(score, 78);
  return (
    <svg viewBox="0 0 240 140" className="mx-auto w-full max-w-xs" role="img" aria-label={`Credit score ${score}, ${band}`}>
      {BANDS.map((b) => <path key={b.label} d={arc(b.from, b.to)} stroke={b.color} strokeWidth={16} fill="none" />)}
      <line x1={120} y1={120} x2={nx} y2={ny} stroke="#0f172a" strokeWidth={3} strokeLinecap="round" />
      <circle cx={120} cy={120} r={6} fill="#0f172a" />
      <text x={24} y={136} fontSize={10} fill="#64748b">300</text>
      <text x={200} y={136} fontSize={10} fill="#64748b">900</text>
    </svg>
  );
}

export default function CreditScorePage() {
  const { data, error, loading, reload } = useApi<Credit>("/credit-score");
  const history = useApi<{ date: string; score: number }[]>("/credit-score/history");
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;
  const maxAbs = Math.max(...data.factors.map((f) => Math.abs(f.contribution)), 1);

  return (
    <>
      <PageHeader title="Credit Score" subtitle="Explainable score from your income, cash flow, dues and repayment history" />
      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="flex flex-col items-center">
          <Gauge score={data.score} band={data.band} />
          <p className="-mt-2 text-4xl font-semibold tabular">{data.score}</p>
          <p className="mt-1 text-sm font-medium text-emerald-700">{data.band}</p>
          <p className="mt-3 text-center text-xs text-slate-500">
            Based on {data.inputs.months_used} months · average income {Math.round(data.inputs.avg_monthly_income).toLocaleString()} a month
          </p>
        </Card>
        <Card className="lg:col-span-2">
          <CardTitle>What moves your score</CardTitle>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">Helping</p>
              <ul className="space-y-2">
                {data.reasons_positive.map((r) => (
                  <li key={r} className="flex gap-2 text-sm"><ArrowUp className="mt-0.5 size-4 shrink-0 text-emerald-600" />{r}</li>
                ))}
                {!data.reasons_positive.length && <li className="text-sm text-slate-500">Nothing yet.</li>}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-700">Hurting</p>
              <ul className="space-y-2">
                {data.reasons_negative.map((r) => (
                  <li key={r} className="flex gap-2 text-sm"><ArrowDown className="mt-0.5 size-4 shrink-0 text-rose-600" />{r}</li>
                ))}
                {!data.reasons_negative.length && <li className="text-sm text-slate-500">Nothing is pulling your score down.</li>}
              </ul>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle right={<span className="text-xs text-slate-500">points vs a typical healthy business</span>}>Factor breakdown</CardTitle>
          <ul className="space-y-3">
            {data.factors.map((f) => (
              <li key={f.key}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{f.label} <span className="text-xs text-slate-400">({Math.round(f.weight * 100)}%)</span></span>
                  <span className={`font-medium tabular ${f.contribution >= 0 ? "text-emerald-700" : "text-rose-600"}`}>
                    {f.contribution >= 0 ? "+" : ""}{Math.round(f.contribution)}
                  </span>
                </div>
                <div className="relative h-2 rounded-full bg-slate-100">
                  <div className="absolute top-0 h-2 w-px bg-slate-300" style={{ left: "50%" }} />
                  <div className={`absolute top-0 h-2 rounded-full ${f.contribution >= 0 ? "bg-emerald-500" : "bg-rose-500"}`}
                    style={{
                      left: f.contribution >= 0 ? "50%" : `${50 - (Math.abs(f.contribution) / maxAbs) * 50}%`,
                      width: `${(Math.abs(f.contribution) / maxAbs) * 50}%`,
                    }} />
                </div>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardTitle>Score history</CardTitle>
          {history.data && history.data.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={history.data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} />
                <YAxis domain={[300, 900]} tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={false} width={36} />
                <Tooltip labelFormatter={(l) => shortDate(String(l))} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Line dataKey="score" stroke="#059669" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : <Loading />}
        </Card>
      </div>
    </>
  );
}
