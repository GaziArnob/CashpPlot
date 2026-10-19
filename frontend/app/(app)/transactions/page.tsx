"use client";

import { useRef, useState } from "react";
import { Camera, Plus, Search, Trash2, Upload } from "lucide-react";
import BankPanel from "@/components/BankPanel";
import Modal, { INPUT } from "@/components/Modal";
import { Badge, Button, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useApi, useBusiness } from "@/lib/hooks";

type Txn = { id: number; date: string; amount: number; type: "income" | "expense"; category: string; description: string | null; source: string };
type Draft = { type: "income" | "expense"; date: string; amount: string; category: string; description: string; source: "manual" | "scan" };

const PAGE = 25;
const SOURCE_COLOR = { manual: "slate", csv: "blue", scan: "amber", system: "green" } as const;
const today = () => new Date().toISOString().slice(0, 10);
const blank = (): Draft => ({ type: "expense", date: today(), amount: "", category: "", description: "", source: "manual" });

function TxnModal({ initial, categories, onClose, onSaved, note }: {
  initial: Draft; categories: { income: string[]; expense: string[] }; onClose: () => void; onSaved: () => void; note?: string;
}) {
  const [d, setD] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("/transactions", { method: "POST", body: JSON.stringify({ ...d, amount: Number(d.amount), description: d.description || null }) });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }
  const options = categories[d.type];
  return (
    <Modal title="Add a transaction" subtitle={note} onClose={onClose}>
      <div className="space-y-3">
        <div className="inline-flex rounded-lg border border-slate-300 p-0.5">
          {(["expense", "income"] as const).map((t) => (
            <button key={t} onClick={() => setD({ ...d, type: t })}
              className={`rounded-md px-4 py-1.5 text-sm font-medium ${d.type === t ? (t === "income" ? "bg-emerald-600 text-white" : "bg-rose-600 text-white") : "text-slate-600"}`}>
              {t === "income" ? "Money in" : "Money out"}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm font-medium text-slate-700">Date
            <input type="date" value={d.date} onChange={(e) => setD({ ...d, date: e.target.value })} className={INPUT} />
          </label>
          <label className="text-sm font-medium text-slate-700">Amount
            <input value={d.amount} inputMode="decimal" onChange={(e) => setD({ ...d, amount: e.target.value.replace(/[^0-9.]/g, "") })} className={INPUT} />
          </label>
        </div>
        <label className="block text-sm font-medium text-slate-700">Category
          <input list="categories" value={d.category} maxLength={60} onChange={(e) => setD({ ...d, category: e.target.value })} className={INPUT}
            placeholder={d.type === "income" ? "e.g. Sales" : "e.g. Inventory"} />
          <datalist id="categories">{options.map((c) => <option key={c} value={c} />)}</datalist>
        </label>
        <label className="block text-sm font-medium text-slate-700">Description (optional)
          <input value={d.description} maxLength={255} onChange={(e) => setD({ ...d, description: e.target.value })} className={INPUT} />
        </label>
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !Number(d.amount) || !d.category.trim() || !d.date} onClick={save}>{busy ? "Saving…" : "Save"}</Button>
        </div>
      </div>
    </Modal>
  );
}

export default function TransactionsPage() {
  const business = useBusiness();
  const cur = business?.currency ?? "USD";
  const [type, setType] = useState("");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [pageState, setPageState] = useState({ key: "", offset: 0 });
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState<Draft | null>(null);
  const [addNote, setAddNote] = useState<string | undefined>();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState<"import" | "scan" | null>(null);
  const csvRef = useRef<HTMLInputElement>(null);
  const imgRef = useRef<HTMLInputElement>(null);

  // A new filter starts again from the first page, without an effect: the page only counts for the filters it was set under.
  const filterKey = [type, category, q, from, to].join("|");
  const offset = pageState.key === filterKey ? pageState.offset : 0;
  const setOffset = (o: number) => setPageState({ key: filterKey, offset: o });
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset), _: String(version) });
  if (type) params.set("type", type);
  if (category) params.set("category", category);
  if (q) params.set("q", q);
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  const list = useApi<{ total: number; items: Txn[] }>(`/transactions?${params}`);
  const cats = useApi<{ income: string[]; expense: string[] }>(`/transactions/categories?_=${version}`);
  const categories = cats.data ?? { income: [], expense: [] };
  const refresh = () => setVersion((v) => v + 1);

  async function importCsv(file: File) {
    setBusy("import");
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api<{ imported: number; skipped: number; errors: { line: number; error: string }[] }>("/transactions/import", { method: "POST", body: form });
      setMessage({ ok: r.imported > 0, text: `Imported ${r.imported} transactions${r.skipped ? `, skipped ${r.skipped}` : ""}.${r.errors[0] ? ` First problem: line ${r.errors[0].line}, ${r.errors[0].error}.` : ""}` });
      refresh();
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "Import failed" });
    } finally {
      setBusy(null);
      if (csvRef.current) csvRef.current.value = "";
    }
  }

  async function scan(file: File) {
    setBusy("scan");
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api<{ suggestion: { date: string | null; amount: number | null; category: string; description: string | null }; engine: string }>("/transactions/scan", { method: "POST", body: form });
      setAddNote(`Read from your receipt with ${r.engine}. Check the details; nothing is saved until you press Save.`);
      setAdding({ type: "expense", date: r.suggestion.date ?? today(), amount: r.suggestion.amount ? String(r.suggestion.amount) : "", category: r.suggestion.category, description: r.suggestion.description ?? "", source: "scan" });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "Could not read the receipt" });
    } finally {
      setBusy(null);
      if (imgRef.current) imgRef.current.value = "";
    }
  }

  async function remove(t: Txn) {
    if (!window.confirm(`Delete this ${t.type === "income" ? "income" : "expense"} of ${money(t.amount, cur)}?`)) return;
    try { await api(`/transactions/${t.id}`, { method: "DELETE" }); refresh(); } catch (e) { setMessage({ ok: false, text: e instanceof Error ? e.message : "Could not delete" }); }
  }

  const total = list.data?.total ?? 0;
  return (
    <>
      <PageHeader title="Transactions" subtitle="Everything that came in and went out"
        right={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={busy !== null} onClick={() => csvRef.current?.click()}><Upload className="size-4" />{busy === "import" ? "Importing…" : "Import CSV"}</Button>
            <Button variant="secondary" disabled={busy !== null} onClick={() => imgRef.current?.click()}><Camera className="size-4" />{busy === "scan" ? "Reading…" : "Scan receipt"}</Button>
            <Button onClick={() => { setAddNote(undefined); setAdding(blank()); }}><Plus className="size-4" /> Add</Button>
            <input ref={csvRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])} />
            <input ref={imgRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && scan(e.target.files[0])} />
          </div>
        } />

      <BankPanel onSynced={refresh} />

      {message && <div className={`mb-4 rounded-lg px-4 py-2.5 text-sm ${message.ok ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>{message.text}</div>}

      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="relative min-w-48 flex-1 text-xs font-medium text-slate-600">Search
            <Search className="absolute bottom-2.5 left-2.5 size-4 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Description" className={`${INPUT} pl-8`} />
          </label>
          <label className="text-xs font-medium text-slate-600">Type
            <select value={type} onChange={(e) => setType(e.target.value)} className={INPUT}>
              <option value="">All</option><option value="income">Money in</option><option value="expense">Money out</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">Category
            <select value={category} onChange={(e) => setCategory(e.target.value)} className={INPUT}>
              <option value="">All</option>
              {[...categories.income, ...categories.expense].filter((c, i, a) => a.indexOf(c) === i).sort().map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={INPUT} /></label>
          <label className="text-xs font-medium text-slate-600">To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={INPUT} /></label>
        </div>
      </Card>

      {list.loading && !list.data ? <Loading /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-5 py-3 font-medium">Date</th>
                <th className="px-3 py-3 font-medium">Description</th>
                <th className="px-3 py-3 font-medium">Category</th>
                <th className="px-3 py-3 text-right font-medium">Amount</th>
                <th className="px-5 py-3 font-medium"><span className="sr-only">Delete</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(list.data?.items ?? []).map((t) => (
                <tr key={t.id} className="hover:bg-slate-50">
                  <td className="px-5 py-2.5 text-slate-600">{shortDate(t.date)}</td>
                  <td className="px-3 py-2.5">{t.description ?? <span className="text-slate-400">—</span>} {t.source !== "manual" && <Badge color={SOURCE_COLOR[t.source as keyof typeof SOURCE_COLOR] ?? "slate"}>{t.source}</Badge>}</td>
                  <td className="px-3 py-2.5 text-slate-600">{t.category}</td>
                  <td className={`px-3 py-2.5 text-right font-medium tabular ${t.type === "income" ? "text-emerald-700" : "text-slate-900"}`}>
                    {t.type === "income" ? "+" : "−"}{money(t.amount, cur)}
                  </td>
                  <td className="px-5 py-2.5 text-right">
                    {t.source !== "system" && <button onClick={() => remove(t)} className="text-slate-300 hover:text-rose-600" aria-label="Delete"><Trash2 className="size-4" /></button>}
                  </td>
                </tr>
              ))}
              {list.data && list.data.items.length === 0 && <tr><td colSpan={5} className="px-5 py-10 text-center text-slate-500">No transactions match. Add one, or import a CSV.</td></tr>}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
            <span>{total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : "0 results"}</span>
            <span className="flex gap-2">
              <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
              <Button variant="secondary" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
            </span>
          </div>
        </Card>
      )}

      {adding && <TxnModal initial={adding} categories={categories} note={addNote} onClose={() => setAdding(null)} onSaved={refresh} />}
    </>
  );
}
