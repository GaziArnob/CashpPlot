"use client";

import { useState, type ReactNode } from "react";
import Modal, { INPUT } from "@/components/Modal";
import { Button, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { useApi } from "@/lib/hooks";

const todayIso = () => new Date().toISOString().slice(0, 10);
const inDays = (n: number) => () => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);
const NEW = "__new__";

type Named = { id: number; name: string };
type Props = { onClose: () => void; onSaved: () => void };

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

const num = (s: string) => s.replace(/[^0-9.]/g, "");

/** One form dialog: shows the error, disables Save while sending, closes and refreshes on success. */
function Form({ title, subtitle, onClose, onSaved, save, canSave, children, cta = "Save" }: {
  title: string; subtitle?: string; onClose: () => void; onSaved: () => void; save: () => Promise<unknown>;
  canSave: boolean; children: ReactNode; cta?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await save();
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={title} subtitle={subtitle} onClose={onClose}>
      <div className="space-y-3">{children}</div>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={busy || !canSave}>{busy ? "Saving…" : cta}</Button>
      </div>
    </Modal>
  );
}

/** A pick-list of existing people/items that also lets the owner type a new one. */
function PickOrNew({ label, items, value, onChange, newName, onNewName, noun }: {
  label: string; items: Named[] | null; value: string; onChange: (v: string) => void;
  newName: string; onNewName: (v: string) => void; noun: string;
}) {
  const none = items !== null && items.length === 0;
  const mode = none ? NEW : value;
  return (
    <>
      <Field label={label}>
        <select className={INPUT} value={mode} onChange={(e) => onChange(e.target.value)} disabled={items === null}>
          {!none && <option value="">Choose…</option>}
          {(items ?? []).map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
          <option value={NEW}>+ New {noun}…</option>
        </select>
      </Field>
      {mode === NEW && (
        <Field label={`New ${noun} name`}>
          <input className={INPUT} value={newName} maxLength={160} autoFocus onChange={(e) => onNewName(e.target.value)} />
        </Field>
      )}
    </>
  );
}

// ---- Ledger ---------------------------------------------------------------------------------------------

export function AddInvoiceModal({ onClose, onSaved }: Props) {
  const customers = useApi<Named[]>("/customers").data;
  const [customer, setCustomer] = useState("");
  const [newName, setNewName] = useState("");
  const [amount, setAmount] = useState("");
  const [issued, setIssued] = useState(todayIso);
  const [due, setDue] = useState(inDays(14));
  const [note, setNote] = useState("");
  const none = customers !== null && customers.length === 0;
  const isNew = none || customer === NEW;
  const ok = Number(amount) > 0 && !!due && !!issued && (isNew ? newName.trim().length > 0 : !!customer);
  return (
    <Form title="Add an invoice" subtitle="Money a customer owes you" onClose={onClose} onSaved={onSaved} canSave={ok}
      save={async () => {
        let id = Number(customer);
        if (isNew) id = (await api<Named>("/customers", { method: "POST", body: JSON.stringify({ name: newName.trim() }) })).id;
        await api("/invoices", { method: "POST", body: JSON.stringify({ customer_id: id, amount: Number(amount), issue_date: issued, due_date: due, note: note || null }) });
      }}>
      <PickOrNew label="Customer" items={customers} value={customer} onChange={setCustomer} newName={newName} onNewName={setNewName} noun="customer" />
      <Field label="Amount"><input className={INPUT} inputMode="decimal" value={amount} onChange={(e) => setAmount(num(e.target.value))} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Issued"><input type="date" className={INPUT} value={issued} onChange={(e) => setIssued(e.target.value)} /></Field>
        <Field label="Due"><input type="date" className={INPUT} value={due} onChange={(e) => setDue(e.target.value)} /></Field>
      </div>
      <Field label="Note (optional)"><input className={INPUT} maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
    </Form>
  );
}

export function RecordPaymentModal({ invoice, currency, onClose, onSaved }: Props & {
  invoice: { id: number; customer_name: string; outstanding: number }; currency: string;
}) {
  const [amount, setAmount] = useState(String(invoice.outstanding));
  const [date, setDate] = useState(todayIso);
  const n = Number(amount);
  return (
    <Form title="Record a payment" subtitle={`${invoice.customer_name} owes ${money(invoice.outstanding, currency)}`}
      onClose={onClose} onSaved={onSaved} canSave={n > 0 && n <= invoice.outstanding + 0.005} cta="Record payment"
      save={() => api(`/invoices/${invoice.id}/payments`, { method: "POST", body: JSON.stringify({ amount: n, paid_date: date }) })}>
      <Field label="Amount received" hint="Less than the full amount keeps the invoice open for the rest.">
        <input className={INPUT} inputMode="decimal" value={amount} onChange={(e) => setAmount(num(e.target.value))} />
      </Field>
      <Field label="Date received"><input type="date" className={INPUT} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
    </Form>
  );
}

export function AddSupplierModal({ onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  return (
    <Form title="Add a supplier" onClose={onClose} onSaved={onSaved} canSave={name.trim().length > 0}
      save={() => api("/suppliers", { method: "POST", body: JSON.stringify({ name: name.trim(), phone: phone || null }) })}>
      <Field label="Supplier name"><input className={INPUT} value={name} maxLength={160} autoFocus onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Phone (optional)" hint="International format, e.g. +14155550123"><input className={INPUT} value={phone} maxLength={30} onChange={(e) => setPhone(e.target.value)} /></Field>
    </Form>
  );
}

export function AddBillModal({ onClose, onSaved }: Props) {
  const suppliers = useApi<Named[]>("/suppliers").data;
  const [supplier, setSupplier] = useState("");
  const [newName, setNewName] = useState("");
  const [amount, setAmount] = useState("");
  const [due, setDue] = useState(inDays(14));
  const [note, setNote] = useState("");
  const none = suppliers !== null && suppliers.length === 0;
  const isNew = none || supplier === NEW;
  const ok = Number(amount) > 0 && !!due && (isNew ? newName.trim().length > 0 : !!supplier);
  return (
    <Form title="Add a bill" subtitle="Money you owe a supplier" onClose={onClose} onSaved={onSaved} canSave={ok}
      save={async () => {
        let id = Number(supplier);
        if (isNew) id = (await api<Named>("/suppliers", { method: "POST", body: JSON.stringify({ name: newName.trim() }) })).id;
        await api("/bills", { method: "POST", body: JSON.stringify({ supplier_id: id, amount: Number(amount), due_date: due, note: note || null }) });
      }}>
      <PickOrNew label="Supplier" items={suppliers} value={supplier} onChange={setSupplier} newName={newName} onNewName={setNewName} noun="supplier" />
      <Field label="Amount"><input className={INPUT} inputMode="decimal" value={amount} onChange={(e) => setAmount(num(e.target.value))} /></Field>
      <Field label="Due date"><input type="date" className={INPUT} value={due} onChange={(e) => setDue(e.target.value)} /></Field>
      <Field label="Note (optional)"><input className={INPUT} maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
    </Form>
  );
}

// ---- Products -------------------------------------------------------------------------------------------

type ProductRow = { id: number; name: string; unit_price: number; unit_cost: number; stock_qty: number };

export function AddProductModal({ onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [cost, setCost] = useState("");
  const [price, setPrice] = useState("");
  const [stock, setStock] = useState("0");
  return (
    <Form title="Add a product" subtitle="What it costs you, what you sell it for, and what you have on hand"
      onClose={onClose} onSaved={onSaved} canSave={name.trim().length > 0 && cost !== "" && price !== ""}
      save={() => api("/products", { method: "POST", body: JSON.stringify({ name: name.trim(), sku: sku || null, unit_cost: Number(cost), unit_price: Number(price), stock_qty: Number(stock) || 0 }) })}>
      <Field label="Product name"><input className={INPUT} value={name} maxLength={160} autoFocus onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="SKU or code (optional)"><input className={INPUT} value={sku} maxLength={60} onChange={(e) => setSku(e.target.value)} /></Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Cost each"><input className={INPUT} inputMode="decimal" value={cost} onChange={(e) => setCost(num(e.target.value))} /></Field>
        <Field label="Price each"><input className={INPUT} inputMode="decimal" value={price} onChange={(e) => setPrice(num(e.target.value))} /></Field>
        <Field label="In stock"><input className={INPUT} inputMode="decimal" value={stock} onChange={(e) => setStock(num(e.target.value))} /></Field>
      </div>
    </Form>
  );
}

export function SaleModal({ product, onClose, onSaved }: Props & { product?: number }) {
  const products = useApi<ProductRow[]>("/products").data;
  const openInvoices = useApi<{ id: number; customer_name: string; outstanding: number }[]>("/invoices?status=open").data;
  const [pid, setPid] = useState(product ? String(product) : "");
  const [qty, setQty] = useState("1");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(todayIso);
  const [kind, setKind] = useState<"cash" | "credit">("cash");
  const [invoice, setInvoice] = useState("");
  const p = products?.find((x) => String(x.id) === pid);
  const ok = !!p && Number(qty) > 0 && Number(qty) <= p.stock_qty + 1e-9 && (kind === "cash" || !!invoice);
  return (
    <Form title="Record a sale" subtitle="Takes the units out of stock. A cash sale also records the money coming in."
      onClose={onClose} onSaved={onSaved} canSave={ok}
      save={() => api("/sale-items", { method: "POST", body: JSON.stringify({
        product_id: Number(pid), date, qty: Number(qty), unit_price: price === "" ? null : Number(price), payment_type: kind,
        invoice_id: kind === "credit" ? Number(invoice) : null }) })}>
      <Field label="Product">
        <select className={INPUT} value={pid} onChange={(e) => setPid(e.target.value)}>
          <option value="">Choose…</option>
          {(products ?? []).map((x) => <option key={x.id} value={x.id}>{x.name} ({x.stock_qty} in stock)</option>)}
        </select>
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Quantity" hint={p ? `Up to ${p.stock_qty}` : undefined}><input className={INPUT} inputMode="decimal" value={qty} onChange={(e) => setQty(num(e.target.value))} /></Field>
        <Field label="Price each" hint={p ? `Usually ${p.unit_price}` : undefined}><input className={INPUT} inputMode="decimal" placeholder={p ? String(p.unit_price) : ""} value={price} onChange={(e) => setPrice(num(e.target.value))} /></Field>
        <Field label="Date"><input type="date" className={INPUT} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      <Field label="Paid how">
        <select className={INPUT} value={kind} onChange={(e) => setKind(e.target.value as "cash" | "credit")}>
          <option value="cash">Paid now (cash or card)</option>
          <option value="credit">On credit (linked to an invoice)</option>
        </select>
      </Field>
      {kind === "credit" && (
        <Field label="Invoice" hint="Add the invoice in the Ledger first if it is not listed.">
          <select className={INPUT} value={invoice} onChange={(e) => setInvoice(e.target.value)}>
            <option value="">Choose…</option>
            {(openInvoices ?? []).map((i) => <option key={i.id} value={i.id}>#{i.id} · {i.customer_name} · {i.outstanding} owed</option>)}
          </select>
        </Field>
      )}
    </Form>
  );
}

export function StockModal({ product, onClose, onSaved }: Props & { product?: number }) {
  const products = useApi<ProductRow[]>("/products").data;
  const [pid, setPid] = useState(product ? String(product) : "");
  const [reason, setReason] = useState<"purchase" | "adjustment" | "write_off">("purchase");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [paid, setPaid] = useState(true);
  const [date, setDate] = useState(todayIso);
  const [direction, setDirection] = useState<"in" | "out">("in");
  const p = products?.find((x) => String(x.id) === pid);
  const removes = reason === "write_off" || (reason === "adjustment" && direction === "out");
  const n = Number(qty);
  const ok = !!p && n > 0 && (!removes || n <= p.stock_qty + 1e-9);
  return (
    <Form title="Add or remove stock" onClose={onClose} onSaved={onSaved} canSave={ok}
      save={() => api("/stock-movements", { method: "POST", body: JSON.stringify({
        product_id: Number(pid), date, qty: removes ? -n : n, reason,
        unit_cost: reason === "purchase" && cost !== "" ? Number(cost) : null, paid_in_cash: reason === "purchase" && paid }) })}>
      <Field label="Product">
        <select className={INPUT} value={pid} onChange={(e) => setPid(e.target.value)}>
          <option value="">Choose…</option>
          {(products ?? []).map((x) => <option key={x.id} value={x.id}>{x.name} ({x.stock_qty} in stock)</option>)}
        </select>
      </Field>
      <Field label="What happened">
        <select className={INPUT} value={reason} onChange={(e) => setReason(e.target.value as typeof reason)}>
          <option value="purchase">Bought more stock</option>
          <option value="adjustment">Stock count correction</option>
          <option value="write_off">Wasted, broken or lost</option>
        </select>
      </Field>
      {reason === "adjustment" && (
        <Field label="Correction">
          <select className={INPUT} value={direction} onChange={(e) => setDirection(e.target.value as "in" | "out")}>
            <option value="in">There is more than the app says</option>
            <option value="out">There is less than the app says</option>
          </select>
        </Field>
      )}
      <div className="grid grid-cols-3 gap-3">
        <Field label="Quantity"><input className={INPUT} inputMode="decimal" value={qty} onChange={(e) => setQty(num(e.target.value))} /></Field>
        {reason === "purchase" && <Field label="Cost each" hint={p ? `Now ${p.unit_cost}` : undefined}><input className={INPUT} inputMode="decimal" placeholder={p ? String(p.unit_cost) : ""} value={cost} onChange={(e) => setCost(num(e.target.value))} /></Field>}
        <Field label="Date"><input type="date" className={INPUT} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      {reason === "purchase" && (
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} /> Paid now (records the money going out)
        </label>
      )}
    </Form>
  );
}
