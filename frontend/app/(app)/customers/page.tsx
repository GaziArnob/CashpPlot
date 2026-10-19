"use client";

import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import Modal, { INPUT } from "@/components/Modal";
import { Badge, Button, Card, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import ConfirmAction from "@/components/payables/ConfirmAction";
import { api } from "@/lib/api";
import { longDate, money, shortDate } from "@/lib/format";
import { useApi, useBusiness } from "@/lib/hooks";

type Customer = {
  id: number; name: string; phone: string | null; email: string | null; risk_level: "low" | "medium" | "high";
  outstanding: number; overdue: number; max_days_overdue: number; invoice_count: number; credit_limit: number | null;
};
type Invoice = { id: number; amount: number; amount_paid: number; issue_date: string; due_date: string; paid_date: string | null; status: "unpaid" | "partial" | "paid"; note: string | null };
type Profile = Customer & { late_payment_share: number; average_days_late: number | null; total_paid: number; invoices: Invoice[] };

const RISK = { low: "green", medium: "amber", high: "red" } as const;
const isoToday = () => new Date().toISOString().slice(0, 10);
const inDays = (n: number) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);

type Editable = { id: number; name: string; phone: string | null; email: string | null };

/** Adds a customer, or edits one when `customer` is given. */
function CustomerForm({ customer, onClose, onSaved }: { customer?: Editable; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(customer?.name ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [email, setEmail] = useState(customer?.email ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body = JSON.stringify({ name: name.trim(), phone: phone.trim() || null, email: email.trim() || null });
      if (customer) await api(`/customers/${customer.id}`, { method: "PUT", body });
      else await api("/customers", { method: "POST", body });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={customer ? "Edit customer" : "Add a customer"} onClose={onClose}>
      <div className="space-y-3">
        <label className="block text-sm font-medium text-slate-700">Name<input value={name} maxLength={160} autoFocus onChange={(e) => setName(e.target.value)} className={INPUT} /></label>
        <label className="block text-sm font-medium text-slate-700">Phone (optional)
          <input value={phone} maxLength={30} placeholder="+8801XXXXXXXXX" onChange={(e) => setPhone(e.target.value)} className={INPUT} />
          <span className="mt-0.5 block text-xs font-normal text-slate-500">Start with + and the country code (for example +8801XXXXXXXXX or +14155550123). WhatsApp reminders need this.</span>
        </label>
        <label className="block text-sm font-medium text-slate-700">Email (optional)<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} /></label>
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button disabled={busy || !name.trim()} onClick={save}>{busy ? "Saving…" : "Save"}</Button></div>
      </div>
    </Modal>
  );
}

function InvoiceRow({ inv, cur, onChanged }: { inv: Invoice; cur: string; onChanged: () => void }) {
  const owed = inv.status === "paid" ? 0 : inv.amount - inv.amount_paid;
  const [now] = useState(() => Date.now()); // read once, so render stays pure
  const days = inv.status === "paid" ? 0 : Math.max(0, Math.floor((now - new Date(inv.due_date + "T00:00:00").getTime()) / 86400000));
  const [paying, setPaying] = useState(false);
  const [amount, setAmount] = useState(String(owed));
  const [error, setError] = useState<string | null>(null);
  async function run(path: string, method: string, body?: object) {
    setError(null);
    try { await api(path, { method, body: body ? JSON.stringify(body) : undefined }); setPaying(false); onChanged(); } catch (e) { setError(e instanceof Error ? e.message : "That didn't work"); throw e; }
  }
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{money(inv.amount, cur)} <span className="font-normal text-slate-500">· due {shortDate(inv.due_date)}</span></p>
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            <Badge color={inv.status === "paid" ? "green" : inv.status === "partial" ? "blue" : days > 0 ? "red" : "slate"}>{inv.status === "unpaid" && days > 0 ? `${days} days overdue` : inv.status}</Badge>
            {inv.status === "partial" && <span>paid {money(inv.amount_paid, cur)}, {money(owed, cur)} left</span>}
            {inv.note && <span>{inv.note}</span>}
          </p>
        </div>
        {inv.status !== "paid" && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setPaying((v) => !v)}>Record payment</Button>
            <ConfirmAction label="Paid in full" prompt={`Record ${money(owed, cur)} received?`} confirmLabel="Yes, received" onConfirm={() => run(`/invoices/${inv.id}/paid`, "PATCH", {})} />
          </div>
        )}
      </div>
      {paying && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input value={amount} inputMode="decimal" onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))} className="w-36 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm tabular" />
          <Button disabled={!Number(amount)} onClick={() => run(`/invoices/${inv.id}/payments`, "POST", { amount: Number(amount) }).catch(() => undefined)}>Save payment</Button>
        </div>
      )}
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
    </li>
  );
}

function ProfileModal({ id, cur, onClose, onChanged }: { id: number; cur: string; onClose: () => void; onChanged: () => void }) {
  const [version, setVersion] = useState(0);
  const p = useApi<Profile>(`/customers/${id}?_=${version}`);
  const [form, setForm] = useState<{ amount: string; issue: string; due: string; note: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const changed = () => { setVersion((v) => v + 1); onChanged(); };

  async function newInvoice() {
    if (!form) return;
    setError(null);
    try {
      await api("/invoices", { method: "POST", body: JSON.stringify({ customer_id: id, amount: Number(form.amount), issue_date: form.issue, due_date: form.due, note: form.note || null }) });
      setForm(null);
      changed();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save"); }
  }
  async function applyLimit() {
    setError(null);
    try { await api(`/customers/${id}/credit-limit`, { method: "POST", body: JSON.stringify({}) }); changed(); } catch (e) { setError(e instanceof Error ? e.message : "Could not set the limit"); }
  }

  return (
    <Modal title={p.data?.name ?? "Customer"} subtitle={[p.data?.email, p.data?.phone].filter(Boolean).join(" · ") || undefined} onClose={onClose} wide>
      {p.loading && !p.data ? <Loading /> : p.error || !p.data ? <ErrorBox message={p.error ?? "Not found"} /> : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Owes you</p><p className="font-semibold tabular">{money(p.data.outstanding, cur)}</p></div>
            <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Overdue</p><p className="font-semibold tabular text-rose-600">{money(p.data.overdue, cur)}</p></div>
            <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Paid late</p><p className="font-semibold tabular">{Math.round(p.data.late_payment_share * 100)}%{p.data.average_days_late !== null && <span className="text-xs font-normal text-slate-500"> · avg {Math.round(p.data.average_days_late)}d</span>}</p></div>
            <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Total paid</p><p className="font-semibold tabular">{money(p.data.total_paid, cur)}</p></div>
          </div>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
            <Button variant="secondary" onClick={() => setEditing(true)}><Pencil className="size-4" /> Edit details</Button>
            <Badge color={RISK[p.data.risk_level]}>{p.data.risk_level} risk</Badge>
            <span className="text-slate-600">Credit limit: {p.data.credit_limit === null ? "not set" : p.data.credit_limit === 0 ? "stop credit" : money(p.data.credit_limit, cur)}</span>
            <Button variant="ghost" onClick={applyLimit}>Apply suggested limit</Button>
          </div>
          {error && <div className="mb-3"><ErrorBox message={error} /></div>}

          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Invoices</p>
            <Button variant="secondary" onClick={() => setForm({ amount: "", issue: isoToday(), due: inDays(30), note: "" })}><Plus className="size-4" /> New invoice</Button>
          </div>
          {form && (
            <div className="mb-3 grid gap-2 rounded-lg border border-slate-200 p-3 sm:grid-cols-4">
              <label className="text-xs font-medium text-slate-600">Amount<input value={form.amount} inputMode="decimal" onChange={(e) => setForm({ ...form, amount: e.target.value.replace(/[^0-9.]/g, "") })} className={INPUT} /></label>
              <label className="text-xs font-medium text-slate-600">Issued<input type="date" value={form.issue} onChange={(e) => setForm({ ...form, issue: e.target.value })} className={INPUT} /></label>
              <label className="text-xs font-medium text-slate-600">Due<input type="date" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} className={INPUT} /></label>
              <label className="text-xs font-medium text-slate-600">Note<input value={form.note} maxLength={255} onChange={(e) => setForm({ ...form, note: e.target.value })} className={INPUT} /></label>
              <div className="flex gap-2 sm:col-span-4"><Button disabled={!Number(form.amount) || !form.issue || !form.due} onClick={newInvoice}>Save invoice</Button><Button variant="ghost" onClick={() => setForm(null)}>Cancel</Button></div>
            </div>
          )}
          {p.data.invoices.length === 0 ? <p className="text-sm text-slate-500">No invoices yet.</p> : (
            <ul className="divide-y divide-slate-100">{p.data.invoices.map((i) => <InvoiceRow key={i.id} inv={i} cur={cur} onChanged={changed} />)}</ul>
          )}
        </>
      )}
      {editing && p.data && <CustomerForm customer={p.data} onClose={() => setEditing(false)} onSaved={changed} />}
    </Modal>
  );
}

export default function CustomersPage() {
  const business = useBusiness();
  const cur = business?.currency ?? "USD";
  const [version, setVersion] = useState(0);
  const list = useApi<Customer[]>(`/customers?_=${version}`);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Editable | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const refresh = () => setVersion((v) => v + 1);

  if (list.loading && !list.data) return <Loading />;
  if (list.error || !list.data) return <ErrorBox message={list.error ?? "No data"} onRetry={list.reload} />;
  const rows = list.data;
  return (
    <>
      <PageHeader title="Customers" subtitle="Who buys from you, who owes you, and how they pay"
        right={<Button onClick={() => setAdding(true)}><Plus className="size-4" /> Add customer</Button>} />
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Customers" value={rows.length} />
        <Stat label="Owed to you" value={money(rows.reduce((s, r) => s + r.outstanding, 0), cur)} />
        <Stat label="Overdue" value={money(rows.reduce((s, r) => s + r.overdue, 0), cur)} tone="warn" />
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-5 py-3 font-medium">Customer</th>
              <th className="px-3 py-3 text-right font-medium">Owes</th>
              <th className="px-3 py-3 text-right font-medium">Overdue</th>
              <th className="px-3 py-3 font-medium">Risk</th>
              <th className="px-3 py-3 text-right font-medium">Credit limit</th>
              <th className="px-3 py-3 text-right font-medium">Invoices</th>
              <th className="px-5 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((c) => (
              <tr key={c.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(c.id)}>
                <td className="px-5 py-3 font-medium">{c.name}<p className="text-xs font-normal text-slate-500">{c.max_days_overdue ? `${c.max_days_overdue} days overdue` : c.email ?? c.phone ?? ""}</p></td>
                <td className="px-3 py-3 text-right tabular">{money(c.outstanding, cur)}</td>
                <td className="px-3 py-3 text-right tabular">{c.overdue ? <span className="text-rose-600">{money(c.overdue, cur)}</span> : "—"}</td>
                <td className="px-3 py-3"><Badge color={RISK[c.risk_level]}>{c.risk_level}</Badge></td>
                <td className="px-3 py-3 text-right tabular text-slate-600">{c.credit_limit === null ? "—" : c.credit_limit === 0 ? "stop" : money(c.credit_limit, cur)}</td>
                <td className="px-3 py-3 text-right tabular text-slate-600">{c.invoice_count}</td>
                <td className="px-5 py-3 text-right">
                  <button aria-label={`Edit ${c.name}`} title="Edit"
                    onClick={(e) => { e.stopPropagation(); setEditing(c); }}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Pencil className="size-4" /></button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={7} className="px-5 py-10 text-center text-slate-500">No customers yet. Add your first one.</td></tr>}
          </tbody>
        </table>
      </Card>
      <p className="mt-3 text-xs text-slate-500">Click a customer to see their invoices, record payments and add new invoices; the pencil edits their name, phone and email. As of {longDate(new Date().toISOString().slice(0, 10))}.</p>
      {adding && <CustomerForm onClose={() => setAdding(false)} onSaved={refresh} />}
      {editing && <CustomerForm customer={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
      {open !== null && <ProfileModal id={open} cur={cur} onClose={() => setOpen(null)} onChanged={refresh} />}
    </>
  );
}
