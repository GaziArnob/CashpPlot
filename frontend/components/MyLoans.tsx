"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import Modal, { INPUT } from "@/components/Modal";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate, money } from "@/lib/format";
import { useApi, useBusiness } from "@/lib/hooks";

type Loan = {
  id: number; lender: string; principal: number; rate: number; tenure_months: number; start_date: string; emi: number;
  status: "active" | "closed"; paid_installments: number; remaining_to_pay: number; overdue_installments: number;
  next_due: { id: number; due_date: string; amount: number } | null;
};
type Installment = { id: number; number: number; due_date: string; amount: number; paid_date: string | null; overdue: boolean };

const todayIso = () => new Date().toISOString().slice(0, 10);
const num = (s: string) => s.replace(/[^0-9.]/g, "");

function monthly(principal: number, ratePct: number, months: number) {
  if (!principal || !months) return 0;
  const r = ratePct / 100 / 12;
  return r === 0 ? principal / months : (principal * r * (1 + r) ** months) / ((1 + r) ** months - 1);
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

function AddLoanModal({ currency, onClose, onSaved }: { currency: string; onClose: () => void; onSaved: () => void }) {
  const [lender, setLender] = useState("");
  const [amount, setAmount] = useState("");
  const [rate, setRate] = useState("");
  const [months, setMonths] = useState("12");
  const [start, setStart] = useState(todayIso);
  const [paid, setPaid] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const emi = monthly(Number(amount), Number(rate), Number(months));
  const ok = lender.trim() && Number(amount) > 0 && rate !== "" && Number(months) >= 1 && Number(paid) <= Number(months);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("/loans", { method: "POST", body: JSON.stringify({
        lender: lender.trim(), principal: Number(amount), rate: Number(rate), tenure_months: Number(months),
        start_date: start, installments_paid: Number(paid) || 0 }) });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the loan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Add a loan you already have" subtitle="Its installments then count in your cash forecast and credit score" onClose={onClose}>
      <div className="space-y-3">
        <Field label="Lender"><input className={INPUT} value={lender} maxLength={160} autoFocus onChange={(e) => setLender(e.target.value)} /></Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Amount borrowed"><input className={INPUT} inputMode="decimal" value={amount} onChange={(e) => setAmount(num(e.target.value))} /></Field>
          <Field label="Interest a year (%)"><input className={INPUT} inputMode="decimal" value={rate} onChange={(e) => setRate(num(e.target.value))} /></Field>
          <Field label="Number of months"><input className={INPUT} inputMode="numeric" value={months} onChange={(e) => setMonths(num(e.target.value))} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Loan start date" hint="The first installment is due a month later"><input type="date" className={INPUT} value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="Installments already paid" hint="So they are not counted as late"><input className={INPUT} inputMode="numeric" value={paid} onChange={(e) => setPaid(num(e.target.value))} /></Field>
        </div>
        {emi > 0 && (
          <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
            About <b>{money(emi, currency)}</b> a month, {money(emi * Number(months) - Number(amount), currency)} total interest.
            Your lender&apos;s figure may differ slightly.
          </p>
        )}
      </div>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button onClick={save} disabled={busy || !ok}>{busy ? "Saving…" : "Save loan"}</Button>
      </div>
    </Modal>
  );
}

function ScheduleModal({ loan, currency, onClose, onChanged }: { loan: Loan; currency: string; onClose: () => void; onChanged: () => void }) {
  const { data, error, loading, reload } = useApi<{ schedule: Installment[] }>(`/loans/${loan.id}`);
  const [err, setErr] = useState<string | null>(null);
  async function pay(i: Installment) {
    setErr(null);
    try {
      await api(`/repayments/${i.id}/paid`, { method: "PATCH" });
      reload();
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update");
    }
  }
  const nextId = data?.schedule.find((i) => !i.paid_date)?.id;
  return (
    <Modal title={`${loan.lender}: installments`} subtitle={`${money(loan.principal, currency)} at ${loan.rate}% for ${loan.tenure_months} months`} onClose={onClose} wide>
      {loading && !data ? <Loading /> : error || !data ? <ErrorBox message={error ?? "No data"} onRetry={reload} /> : (
        <ul className="divide-y divide-slate-100 text-sm">
          {data.schedule.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="w-8 text-slate-400">{i.number}.</span>
              <span className="flex-1">{longDate(i.due_date)}</span>
              <span className="w-28 text-right tabular">{money(i.amount, currency)}</span>
              <span className="w-40 text-right">
                {i.paid_date ? <Badge color="green">paid {i.paid_date}</Badge>
                  : i.overdue ? <Badge color="red">late</Badge>
                  : i.id === nextId ? <Button variant="secondary" className="px-2.5" onClick={() => pay(i)}>Mark paid</Button>
                  : <span className="text-xs text-slate-400">upcoming</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {data?.schedule.some((i) => i.overdue) && (
        <p className="mt-3 text-xs text-slate-500">Late installments show as late until you mark them paid, oldest first. Marking one paid records the money going out today.</p>
      )}
      {err && <div className="mt-3"><ErrorBox message={err} /></div>}
    </Modal>
  );
}

/** Loans the business already has. Adding one makes its installments part of the forecast and the credit score. */
export default function MyLoans({ onChanged }: { onChanged: () => void }) {
  const cur = useBusiness()?.currency ?? "USD";
  const { data, error, loading, reload } = useApi<Loan[]>("/loans");
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<Loan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const changed = () => { reload(); onChanged(); };

  async function remove(l: Loan) {
    if (!window.confirm(`Remove the ${l.lender} loan? Payments you already recorded for it stay in your transactions.`)) return;
    setErr(null);
    try { await api(`/loans/${l.id}`, { method: "DELETE" }); changed(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not remove"); }
  }

  return (
    <Card className="mb-6">
      <CardTitle right={<Button onClick={() => setAdding(true)}><Plus className="size-4" /> Add a loan</Button>}>My loans</CardTitle>
      {loading && !data ? <Loading /> : error || !data ? <ErrorBox message={error ?? "No data"} onRetry={reload} /> : data.length === 0 ? (
        <p className="text-sm text-slate-500">
          No loans recorded. If you already repay a loan, add it here so your forecast and the safe-borrowing figure above take its installments into account.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {data.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
              <div>
                <p className="font-medium">
                  {l.lender} <span className="font-normal text-slate-500">· {money(l.principal, cur)} at {l.rate}%</span>{" "}
                  {l.status === "closed" ? <Badge color="slate">paid off</Badge> : l.overdue_installments > 0 ? <Badge color="red">{l.overdue_installments} late</Badge> : <Badge color="green">on track</Badge>}
                </p>
                <p className="text-xs text-slate-500">
                  {money(l.emi, cur)} a month · {l.paid_installments} of {l.tenure_months} paid
                  {l.status === "active" && ` · ${money(l.remaining_to_pay, cur)} left to pay`}
                  {l.next_due && ` · next ${longDate(l.next_due.due_date)}`}
                </p>
              </div>
              <div className="flex gap-1">
                <Button variant="secondary" className="px-2.5" onClick={() => setOpen(l)}>Installments</Button>
                <Button variant="ghost" className="px-2.5" onClick={() => remove(l)}>Remove</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {err && <div className="mt-3"><ErrorBox message={err} /></div>}
      {adding && <AddLoanModal currency={cur} onClose={() => setAdding(false)} onSaved={changed} />}
      {open && <ScheduleModal loan={open} currency={cur} onClose={() => setOpen(null)} onChanged={changed} />}
    </Card>
  );
}
