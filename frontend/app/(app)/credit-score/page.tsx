"use client";

import Link from "next/link";
import { ArrowDown, ArrowUp, Clock, Info, Target } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Card, CardTitle, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { shortDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Credit } from "@/lib/types";

const BANDS = [
  { from: 300, to: 550, color: "#f2817f", label: "Needs improvement" },
  { from: 550, to: 650, color: "#f59e0b", label: "Fair" },
  { from: 650, to: 750, color: "#4cc38a", label: "Good" },
  { from: 750, to: 900, color: "#8b72e0", label: "Excellent" },
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
      <line x1={120} y1={120} x2={nx} y2={ny} stroke="#ecebef" strokeWidth={3} strokeLinecap="round" />
      <circle cx={120} cy={120} r={6} fill="#ecebef" />
      <text x={24} y={136} fontSize={10} fill="#908d98">300</text>
      <text x={200} y={136} fontSize={10} fill="#908d98">900</text>
    </svg>
  );
}

type ScorePlan = {
  score: number; band: string; disclaimer: string; needs_data: string[];
  next_band: { band: string; score: number; points_needed: number; reachable: boolean } | null;
  next_loan: { name: string; min_score: number; points_needed: number; reachable: boolean } | null;
  actions: { id: string; title: string; detail: string; points: number; link: string; kind: "action" | "time" }[];
  if_you_do_everything: { score: number; band: string; points: number; unlocks: string[] };
};

function ImproveCard() {
  const { data: p, error, loading, reload } = useApi<ScorePlan>("/credit-score/plan");
  if (loading && !p) return <Loading />;
  if (error || !p) return <ErrorBox message={error ?? "No data"} onRetry={reload} />;
  const everything = p.if_you_do_everything;
  return (
    <Card className="mb-6">
      <CardTitle right={<Target className="size-4 text-emerald-700" />}>How to raise your score</CardTitle>
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        {p.next_band ? (
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm">
            <b>{p.next_band.points_needed} points</b> to reach <b>{p.next_band.band}</b> ({p.next_band.score}).{" "}
            <span className="text-slate-500">{p.next_band.reachable ? "The steps below can get you there." : "The steps below help but may not be enough alone."}</span>
          </p>
        ) : <p className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-900">You are in the top band. Keep doing what you are doing.</p>}
        {p.next_loan ? (
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm">
            <b>{p.next_loan.points_needed} points</b> to unlock the <b>{p.next_loan.name}</b> (needs {p.next_loan.min_score}).{" "}
            <Link href="/loan" className="font-medium text-emerald-700 hover:underline">Loan Center</Link>
          </p>
        ) : <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">Your score already meets every loan type&apos;s minimum.</p>}
      </div>

      {p.actions.length > 0 ? (
        <ul className="divide-y divide-slate-100">
          {p.actions.map((a) => (
            <li key={a.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm font-medium">
                  {a.kind === "time" && <Clock className="size-4 text-slate-400" />}{a.title}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">{a.detail}</p>
              </div>
              <div className="flex items-center gap-3">
                <Badge color="green">+{a.points} points</Badge>
                {a.kind === "action" && <Link href={a.link} className="text-sm font-medium text-emerald-700 hover:underline">Go</Link>}
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-slate-500">No single step stands out right now. Keep your records up to date and the score follows.</p>}

      {everything.points > 0 && (
        <p className="mt-3 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          Do the steps above (not counting time) and your score could reach about <b>{everything.score}</b> ({everything.band}), {everything.points} points higher.
          {everything.unlocks.length > 0 && <> That would unlock: {everything.unlocks.join(", ")}.</>}
        </p>
      )}
      {p.needs_data.length > 0 && (
        <div className="mt-3 text-sm">
          <p className="font-medium">To make the score more accurate, add:</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-600">{p.needs_data.map((m) => <li key={m}>{m}</li>)}</ul>
        </div>
      )}
      <p className="mt-3 text-xs text-slate-500">{p.disclaimer}</p>
    </Card>
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
      {data.confidence && data.confidence.level !== "high" && (
        <div className={`mb-6 rounded-xl border px-5 py-4 text-sm ${data.confidence.level === "low" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-sky-200 bg-sky-50 text-sky-900"}`}>
          <p className="flex items-center gap-2 font-medium">
            <Info className="size-4 shrink-0" />
            {data.confidence.level === "low" ? "This score is only a starting point: there is too little data behind it yet." : "This score will get steadier as you add more records."}
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-9">
            {data.confidence.missing.map((m) => <li key={m}>{m}</li>)}
          </ul>
          <p className="mt-3 pl-6 text-xs">
            Add data in <Link href="/transactions" className="font-medium underline">Transactions</Link>,{" "}
            <Link href="/ledger" className="font-medium underline">Ledger</Link> and{" "}
            <Link href="/loan" className="font-medium underline">Loan Center</Link>. The score updates by itself.
          </p>
        </div>
      )}
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

      <ImproveCard />

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
                {f.tip && <p className="mb-1.5 text-xs text-slate-500">{f.tip}</p>}
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
                <CartesianGrid stroke="#312e35" vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: "#908d98" }} tickLine={false} />
                <YAxis domain={[300, 900]} tick={{ fontSize: 11, fill: "#908d98" }} tickLine={false} axisLine={false} width={36} />
                <Tooltip labelFormatter={(l) => shortDate(String(l))} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Line dataKey="score" stroke="#8b72e0" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : history.data ? (
            <p className="text-sm text-slate-500">
              No history yet. A new point is saved each day your score is calculated, so this line fills in over the next few days.
            </p>
          ) : <Loading />}
        </Card>
      </div>
    </>
  );
}
