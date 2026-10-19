"use client";

import { useState } from "react";
import { Download, Pencil, Plus, Target, Trash2, TrendingDown, TrendingUp } from "lucide-react";
import Modal, { INPUT } from "@/components/Modal";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { api, downloadFile } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useApi, useBusiness } from "@/lib/hooks";

type Pnl = { month: string; income: Record<string, number>; expense: Record<string, number>; total_income: number; total_expense: number; net_profit: number; margin_pct: number | null };
type Insight = { category: string; direction: "up" | "down" | "share"; message: string; change_pct: number | null };
type Goal = { id: number; title: string; target_amount: number; current_amount: number; deadline: string | null };

const thisMonth = () => new Date().toISOString().slice(0, 7);

function Breakdown({ title, rows, total, color, cur }: { title: string; rows: Record<string, number>; total: number; color: string; cur: string }) {
  const entries = Object.entries(rows);
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      {entries.length === 0 ? <p className="text-sm text-slate-500">Nothing recorded.</p> : (
        <ul className="space-y-2.5">
          {entries.map(([name, value]) => (
            <li key={name}>
              <div className="flex justify-between text-sm"><span>{name}</span><span className="tabular">{money(value, cur)}</span></div>
              <div className="mt-1 h-1.5 rounded-full bg-slate-100"><div className="ff-grow h-1.5 rounded-full" style={{ width: `${total ? Math.max(2, (100 * value) / total) : 0}%`, background: color }} /></div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function GoalModal({ goal, onClose, onSaved }: { goal: Goal | null; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(goal?.title ?? "");
  const [target, setTarget] = useState(goal ? String(goal.target_amount) : "");
  const [current, setCurrent] = useState(goal ? String(goal.current_amount) : "0");
  const [deadline, setDeadline] = useState(goal?.deadline ?? "");
  const [error, setError] = useState<string | null>(null);
  async function save() {
    setError(null);
    const body = JSON.stringify({ title, target_amount: Number(target), current_amount: Number(current) || 0, deadline: deadline || null });
    try {
      await api(goal ? `/goals/${goal.id}` : "/goals", { method: goal ? "PUT" : "POST", body });
      onSaved();
      onClose();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save"); }
  }
  return (
    <Modal title={goal ? "Edit goal" : "New savings goal"} onClose={onClose}>
      <div className="space-y-3">
        <label className="block text-sm font-medium text-slate-700">Goal<input value={title} maxLength={160} onChange={(e) => setTitle(e.target.value)} className={INPUT} placeholder="e.g. Three months of expenses in reserve" /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm font-medium text-slate-700">Target<input value={target} inputMode="decimal" onChange={(e) => setTarget(e.target.value.replace(/[^0-9.]/g, ""))} className={INPUT} /></label>
          <label className="text-sm font-medium text-slate-700">Saved so far<input value={current} inputMode="decimal" onChange={(e) => setCurrent(e.target.value.replace(/[^0-9.]/g, ""))} className={INPUT} /></label>
        </div>
        <label className="block text-sm font-medium text-slate-700">Deadline (optional)<input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className={INPUT} /></label>
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button disabled={!title.trim() || !Number(target)} onClick={save}>Save</Button></div>
      </div>
    </Modal>
  );
}

export default function ReportsPage() {
  const business = useBusiness();
  const cur = business?.currency ?? "USD";
  const [month, setMonth] = useState(thisMonth());
  const [version, setVersion] = useState(0);
  const pnl = useApi<Pnl>(`/reports/pnl?month=${month}`);
  const insights = useApi<Insight[]>("/reports/insights");
  const goals = useApi<Goal[]>(`/goals?_=${version}`);
  const [editing, setEditing] = useState<Goal | null | undefined>(undefined);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pdf() {
    setDownloading(true);
    setError(null);
    try { await downloadFile(`/reports/export?month=${month}`, `profit-and-loss-${month}.pdf`); } catch (e) { setError(e instanceof Error ? e.message : "Download failed"); } finally { setDownloading(false); }
  }
  async function removeGoal(g: Goal) {
    if (!window.confirm(`Delete the goal “${g.title}”?`)) return;
    try { await api(`/goals/${g.id}`, { method: "DELETE" }); setVersion((v) => v + 1); } catch (e) { setError(e instanceof Error ? e.message : "Could not delete"); }
  }

  const p = pnl.data;
  return (
    <>
      <PageHeader title="Reports" subtitle="Profit and loss, spending changes and savings goals"
        right={
          <div className="flex flex-wrap items-center gap-2">
            <input type="month" value={month} max={thisMonth()} onChange={(e) => e.target.value && setMonth(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" />
            <Button variant="secondary" onClick={pdf} disabled={downloading}><Download className="size-4" />{downloading ? "Preparing…" : "Download PDF"}</Button>
          </div>
        } />
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}

      {pnl.loading && !p ? <Loading /> : pnl.error || !p ? <ErrorBox message={pnl.error ?? "No data"} onRetry={pnl.reload} /> : (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-4">
            <Stat label="Money in" value={money(p.total_income, cur)} tone="good" />
            <Stat label="Money out" value={money(p.total_expense, cur)} />
            <Stat label="Net profit" value={money(p.net_profit, cur)} tone={p.net_profit >= 0 ? "good" : "bad"} />
            <Stat label="Margin" value={p.margin_pct === null ? "—" : `${p.margin_pct}%`} hint="Net profit ÷ money in" />
          </div>
          <Card className="mb-6">
            <CardTitle>Profit and loss, {p.month}</CardTitle>
            <div className="grid gap-8 md:grid-cols-2">
              <Breakdown title="Money in" rows={p.income} total={p.total_income} color="#8b72e0" cur={cur} />
              <Breakdown title="Money out" rows={p.expense} total={p.total_expense} color="#f2817f" cur={cur} />
            </div>
          </Card>
        </>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Spending changes</CardTitle>
          {insights.loading && !insights.data ? <Loading /> : insights.error ? <ErrorBox message={insights.error} /> : (
            <ul className="space-y-3">
              {(insights.data ?? []).map((i, k) => (
                <li key={k} className="flex gap-3 text-sm">
                  {i.direction === "up" ? <TrendingUp className="mt-0.5 size-4 shrink-0 text-rose-600" /> : i.direction === "down" ? <TrendingDown className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <Target className="mt-0.5 size-4 shrink-0 text-slate-400" />}
                  <span className="flex-1 text-slate-700">{i.message}</span>
                  {i.change_pct !== null && <Badge color={i.direction === "up" ? "red" : "green"}>{i.change_pct > 0 ? "+" : ""}{i.change_pct}%</Badge>}
                </li>
              ))}
              {insights.data?.length === 0 && <li className="text-sm text-slate-500">Not enough history yet to spot changes.</li>}
            </ul>
          )}
        </Card>

        <Card>
          <CardTitle right={<Button variant="secondary" onClick={() => setEditing(null)}><Plus className="size-4" /> New goal</Button>}>Savings goals</CardTitle>
          {goals.loading && !goals.data ? <Loading /> : goals.error ? <ErrorBox message={goals.error} /> : (
            <ul className="space-y-4">
              {(goals.data ?? []).map((g) => {
                const pct = Math.min(100, Math.round((100 * g.current_amount) / g.target_amount));
                return (
                  <li key={g.id}>
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium">{g.title}</p>
                      <span className="flex gap-1.5">
                        <button onClick={() => setEditing(g)} className="text-slate-400 hover:text-slate-700" aria-label="Edit"><Pencil className="size-4" /></button>
                        <button onClick={() => removeGoal(g)} className="text-slate-400 hover:text-rose-600" aria-label="Delete"><Trash2 className="size-4" /></button>
                      </span>
                    </div>
                    <div className="mt-1.5 h-2 rounded-full bg-slate-100"><div className="ff-grow h-2 rounded-full bg-emerald-500" style={{ width: `${pct}%` }} /></div>
                    <p className="mt-1 text-xs text-slate-500">{money(g.current_amount, cur)} of {money(g.target_amount, cur)} ({pct}%){g.deadline && ` · by ${shortDate(g.deadline)}`}</p>
                  </li>
                );
              })}
              {goals.data?.length === 0 && <li className="text-sm text-slate-500">No goals yet. Set one to build a cash cushion.</li>}
            </ul>
          )}
        </Card>
      </div>
      {editing !== undefined && <GoalModal goal={editing} onClose={() => setEditing(undefined)} onSaved={() => setVersion((v) => v + 1)} />}
    </>
  );
}
