"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, BellRing, CheckCircle2, Loader2, MessageSquareText, ShieldCheck, Sparkles } from "lucide-react";
import ActionPlan from "@/components/ActionPlan";
import BalanceChart from "@/components/BalanceChart";
import ProductQuadrant, { CLASS_META, QUADRANT_CLASSES } from "@/components/ProductQuadrant";
import ReminderModal, { type ReminderDraft } from "@/components/ReminderModal";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate, money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ActionPlan as Plan, AdvisorSummary, RecoveryCustomer, Reminder } from "@/lib/types";

type Lang = "en" | "bn";

const ACTION_COLOR = {
  stop_credit: "red", visit: "red", call: "amber", discount: "blue", send_reminder: "slate", wait: "green",
} as const;

function LangToggle({ lang, onChange }: { lang: Lang; onChange: (l: Lang) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5">
      {(["en", "bn"] as const).map((l) => (
        <button key={l} onClick={() => onChange(l)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${lang === l ? "bg-emerald-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>
          {l === "en" ? "English" : "বাংলা"}
        </button>
      ))}
    </div>
  );
}

function Advice({ s, loading }: { s: AdvisorSummary; loading: boolean }) {
  const byAi = s.advice.generated_by !== "template";
  return (
    <Card className="mb-6 border-emerald-200 bg-gradient-to-br from-emerald-50 to-white">
      <div className="flex gap-3">
        <Sparkles className="mt-0.5 size-5 shrink-0 text-emerald-600" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-emerald-900">{s.advice.lang === "bn" ? "আজকের পরামর্শ" : "Today's advice"}</p>
            {loading && <Loader2 className="size-4 animate-spin text-emerald-600" />}
          </div>
          <p className={`mt-2 leading-relaxed text-slate-800 ${s.advice.lang === "bn" ? "text-[15px]" : "text-sm"}`}>{s.advice.text}</p>
          <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            <ShieldCheck className="size-3.5 text-emerald-600" />
            {byAi ? `Written by free AI (${s.advice.generated_by}); every figure checked against your numbers`
              : s.advice.llm_rejected ? "AI answer had an unverified figure, so this summary comes straight from your numbers"
                : "Written from your numbers (no AI connected)"}
          </p>
        </div>
      </div>
    </Card>
  );
}

function Collections({ s, onDraft, busy }: {
  s: AdvisorSummary; onDraft: (c: RecoveryCustomer, lang: Lang) => void; busy: string | null;
}) {
  return (
    <ul className="divide-y divide-slate-100">
      {s.collections.map((c) => (
        <li key={c.customer_id} className="flex flex-wrap items-center gap-3 py-3">
          <span className="flex size-6 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold">{c.rank}</span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{c.customer_name}</p>
            <p className="text-xs text-slate-500">
              {money(c.outstanding)}{c.max_days_overdue ? ` · ${c.max_days_overdue} days overdue` : " · not due"}
              {` · ${Math.round(c.p_pay_7d * 100)}% pays in 7 days`}
            </p>
          </div>
          <Badge color={ACTION_COLOR[c.action]}>{c.action_label}</Badge>
          <div className="flex gap-1">
            {(["en", "bn"] as const).map((l) => (
              <Button key={l} variant="secondary" className="px-2" disabled={busy !== null} onClick={() => onDraft(c, l)}>
                <MessageSquareText className="size-3.5" />
                {busy === `${c.customer_id}:${l}` ? "…" : l === "en" ? "EN" : "বাংলা"}
              </Button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function AdvisorPage() {
  const [lang, setLang] = useState<Lang>("en");
  const summary = useApi<AdvisorSummary>(`/cash-advisor/summary?lang=${lang}`);
  const plan = useApi<Plan>("/action-plan");
  const [draft, setDraft] = useState<ReminderDraft | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [jobMsg, setJobMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function draftReminder(c: RecoveryCustomer, l: Lang) {
    setBusy(`${c.customer_id}:${l}`);
    setError(null);
    try {
      const reminder = await api<Reminder>(`/collections/${c.customer_id}/reminder?lang=${l}`, { method: "POST" });
      setDraft({ reminder, customer: c.customer_name });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not draft the reminder");
    } finally {
      setBusy(null);
    }
  }

  async function runDailyCheck() {
    setBusy("job");
    setError(null);
    try {
      const r = await api<{ alert_sent: boolean; alert_message: string | null; cash_crunch: unknown }>(
        "/jobs/daily/run", { method: "POST" });
      setJobMsg(r.alert_message
        ? `${r.alert_sent ? "Alert sent" : "Already alerted today"}: ${r.alert_message}`
        : "Daily check done: no cash crunch in the next 30 days.");
      plan.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Daily check failed");
    } finally {
      setBusy(null);
    }
  }

  const s = summary.data;
  if (summary.loading && !s) return <><PageHeader title="Cash Advisor" /><Loading label="Working out your plan" /></>;
  if (summary.error || !s) return <ErrorBox message={summary.error ?? "No data"} onRetry={summary.reload} />;
  const g = s.gap_card;

  return (
    <>
      <PageHeader title="Cash Advisor" subtitle={`Your cash situation and what to do about it · ${longDate(s.as_of)}`}
        right={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={runDailyCheck} disabled={busy !== null}>
              <BellRing className="size-4" />{busy === "job" ? "Checking…" : "Run daily check"}
            </Button>
            <LangToggle lang={lang} onChange={setLang} />
          </div>
        } />

      {jobMsg && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
          <BellRing className="mt-0.5 size-4 shrink-0" /> <span className="flex-1">{jobMsg}</span>
          <button onClick={() => setJobMsg(null)} className="text-sky-700 underline">close</button>
        </div>
      )}
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}

      <Advice s={s} loading={summary.loading} />

      {/* Gap card */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {g.first_shortage ? (
          <Card className="border-rose-200 bg-rose-50 sm:col-span-2">
            <div className="flex gap-3">
              <AlertTriangle className="mt-0.5 size-5 shrink-0 text-rose-600" />
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-rose-700">Cash gap</p>
                <p className="mt-1 text-2xl font-semibold text-rose-700 tabular">{money(g.first_shortage.gap)}</p>
                <p className="mt-1 text-sm text-rose-900">
                  needed by <b>{longDate(g.first_shortage.date)}</b>. The deepest point in 30 days is {money(g.largest_gap)}
                  {" "}short ({g.shortage_days} days below your safety level).
                </p>
              </div>
            </div>
          </Card>
        ) : (
          <Card className="border-emerald-200 bg-emerald-50 sm:col-span-2">
            <div className="flex gap-3">
              <CheckCircle2 className="mt-0.5 size-5 text-emerald-600" />
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-emerald-700">No cash gap</p>
                <p className="mt-1 text-sm text-emerald-900">Cash stays above your safety level for the next 30 days.</p>
              </div>
            </div>
          </Card>
        )}
        <Stat label="Cash today" value={money(g.balance)} hint={`Safety level ${money(g.threshold)}`} />
        <Stat label="Plan brings in" value={money(g.plan_expected)} tone={g.gap_covered ? "good" : "warn"}
          hint={g.gap_covered ? "Covers the gap" : `${money(g.remaining_gap)} still missing`} />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardTitle right={<Link href="/cashflow" className="text-xs font-medium text-emerald-700 hover:underline">Details</Link>}>
            30-day cash forecast
          </CardTitle>
          <BalanceChart data={s.forecast} threshold={g.threshold} showBand height={260} />
        </Card>
        <Card className="xl:col-span-2">
          <CardTitle right={<Link href="/ledger" className="text-xs font-medium text-emerald-700 hover:underline">All customers</Link>}>
            Collect first
          </CardTitle>
          <Collections s={s} onDraft={draftReminder} busy={busy} />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardTitle right={plan.loading && <Loader2 className="size-4 animate-spin text-slate-400" />}>Action plan</CardTitle>
          {plan.error ? <ErrorBox message={plan.error} onRetry={plan.reload} />
            : plan.data ? <ActionPlan plan={plan.data} onChanged={plan.reload} /> : <Loading />}
        </Card>
        <Card className="xl:col-span-2">
          <CardTitle right={<Link href="/products" className="text-xs font-medium text-emerald-700 hover:underline">Products</Link>}>
            Product quadrant
          </CardTitle>
          <ProductQuadrant products={s.products.items} thresholds={s.products.thresholds} height={260} />
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
            {QUADRANT_CLASSES.map((c) => (
              <span key={c} className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full" style={{ background: CLASS_META[c].color }} />
                {CLASS_META[c].label} ({s.products.counts[c]})
              </span>
            ))}
          </div>
          <p className="mt-3 text-sm text-slate-600">
            {money(s.products.cash_tied_in_slow_and_dead)} is stuck in slow and dead stock; clearing it could free up to{" "}
            {money(s.products.cash_freed_if_cleared)}.
          </p>
        </Card>
      </div>

      {draft && <ReminderModal draft={draft} onClose={() => setDraft(null)} />}
    </>
  );
}
