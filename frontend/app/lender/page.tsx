"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Wallet } from "lucide-react";
import { Card, CardTitle, ErrorBox, Button } from "@/components/ui";
import { API_URL } from "@/lib/api";
import { money } from "@/lib/format";

type View = {
  business: string; lender: string; scope: string[]; expires_at: string;
  credit_score?: { score: number; band: string; reasons_positive: string[]; reasons_negative: string[] };
  pnl_last_month?: { revenue?: number; expenses?: number; net_profit?: number; [k: string]: unknown };
  cash_forecast?: { start_balance: number; min_balance: number; first_shortage: string | null };
};

export default function LenderPage() {
  const [token, setToken] = useState("");
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function open(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setView(null);
    try {
      const r = await fetch(`${API_URL}/lender/view`, { headers: { "X-Lender-Token": token.trim() } });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not open this link");
      setView(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open this link");
    } finally {
      setBusy(false);
    }
  }

  const p = view?.pnl_last_month;
  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <Link href="/" className="mb-6 flex items-center gap-2">
        <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-600 text-white"><Wallet className="size-4" /></div>
        <span className="text-lg font-semibold tracking-tight">CashPilot</span>
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Lender view</h1>
      <p className="mb-6 mt-1 text-sm text-slate-500">Read-only information a business chose to share with you. Paste the access token you were given.</p>
      <form onSubmit={open} className="mb-6 flex gap-2">
        <input required value={token} onChange={(e) => setToken(e.target.value)} placeholder="Access token" autoComplete="off"
          className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" />
        <Button type="submit" disabled={busy}>{busy ? "Opening…" : "Open"}</Button>
      </form>
      {error && <ErrorBox message={error} />}
      {view && (
        <div className="space-y-4">
          <Card>
            <p className="text-lg font-semibold">{view.business}</p>
            <p className="text-sm text-slate-500">Shared with {view.lender} until {view.expires_at.slice(0, 10)}. Only the items below were shared.</p>
          </Card>
          {view.credit_score && (
            <Card>
              <CardTitle>Credit score</CardTitle>
              <p className="text-3xl font-semibold tabular">{view.credit_score.score} <span className="text-base font-normal text-slate-500">{view.credit_score.band}</span></p>
              <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <ul className="list-disc pl-5 text-emerald-800">{view.credit_score.reasons_positive.map((x) => <li key={x}>{x}</li>)}</ul>
                <ul className="list-disc pl-5 text-rose-800">{view.credit_score.reasons_negative.map((x) => <li key={x}>{x}</li>)}</ul>
              </div>
            </Card>
          )}
          {p && (
            <Card>
              <CardTitle>Profit &amp; loss, last month</CardTitle>
              <dl className="grid grid-cols-3 gap-3 text-sm">
                {Object.entries(p).filter(([, v]) => typeof v === "number").slice(0, 6).map(([k, v]) => (
                  <div key={k}><dt className="text-xs uppercase text-slate-500">{k.replace(/_/g, " ")}</dt><dd className="font-semibold tabular">{money(v as number)}</dd></div>
                ))}
              </dl>
            </Card>
          )}
          {view.cash_forecast && (
            <Card>
              <CardTitle>30-day cash forecast</CardTitle>
              <p className="text-sm">Starting balance {money(view.cash_forecast.start_balance)}, lowest expected {money(view.cash_forecast.min_balance)}
                {view.cash_forecast.first_shortage ? `, first shortage ${view.cash_forecast.first_shortage}` : ", no shortage expected"}.</p>
            </Card>
          )}
          <p className="text-xs text-slate-500">Figures come from the business&apos;s own records and a deterministic model. They are not verified by CashPilot and are not an approval or a guarantee.</p>
        </div>
      )}
    </div>
  );
}
