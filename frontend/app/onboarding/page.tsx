"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, Download, Upload } from "lucide-react";
import { Button, Card, ErrorBox } from "@/components/ui";
import { api, getToken } from "@/lib/api";

const INPUT = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100";
const TYPES = ["Retail", "Wholesale", "Restaurant & food", "Services", "Manufacturing", "Other"];
const CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "SGD", "INR"];
const STEPS = ["Your business", "Your cash", "Add your records"];
const SAMPLE_CSV = "date,amount,type,category,description\n2026-01-05,1200,income,Sales,Weekend sales\n2026-01-06,-450,expense,Inventory,Stock purchase\n2026-01-07,-90,expense,Utilities,Electricity\n";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [type, setType] = useState(TYPES[0]);
  const [currency, setCurrency] = useState("USD");
  const [startedAt, setStartedAt] = useState(() => new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10));
  const [balance, setBalance] = useState("0");
  const [threshold, setThreshold] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  async function createBusiness() {
    setBusy(true);
    setError(null);
    try {
      await api("/onboarding", {
        method: "POST",
        body: JSON.stringify({ name, type, currency, started_at: startedAt, opening_balance: Number(balance) || 0, cash_threshold: Number(threshold) || 0 }),
      });
      setStep(2);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not save";
      if (msg.includes("already set up")) router.replace("/dashboard");
      else setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api<{ imported: number; skipped: number }>("/transactions/import", { method: "POST", body: form });
      setImported(`Imported ${r.imported} transactions${r.skipped ? `, skipped ${r.skipped} rows that didn't look right` : ""}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  function downloadSample() {
    const url = URL.createObjectURL(new Blob([SAMPLE_CSV], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "sample-transactions.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Set up your business</h1>
      <p className="mt-1 text-sm text-slate-500">Three quick steps. You can change everything later in Settings.</p>

      <ol className="my-6 flex items-center gap-2">
        {STEPS.map((s, i) => (
          <li key={s} className="flex flex-1 items-center gap-2">
            <span className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${i < step ? "bg-emerald-600 text-white" : i === step ? "border-2 border-emerald-600 text-emerald-700" : "bg-slate-100 text-slate-400"}`}>
              {i < step ? <Check className="size-4" /> : i + 1}
            </span>
            <span className={`hidden text-xs sm:block ${i === step ? "font-medium text-slate-900" : "text-slate-500"}`}>{s}</span>
            {i < STEPS.length - 1 && <span className="h-px flex-1 bg-slate-200" />}
          </li>
        ))}
      </ol>

      <Card>
        {step === 0 && (
          <div className="space-y-4">
            <label className="block text-sm font-medium text-slate-700">Business name
              <input value={name} maxLength={160} onChange={(e) => setName(e.target.value)} className={INPUT} placeholder="e.g. Evergreen Traders" />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-medium text-slate-700">Type of business
                <select value={type} onChange={(e) => setType(e.target.value)} className={INPUT}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
              </label>
              <label className="block text-sm font-medium text-slate-700">Currency
                <select value={currency} onChange={(e) => setCurrency(e.target.value)} className={INPUT}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select>
              </label>
            </div>
            <label className="block text-sm font-medium text-slate-700">When did the business start?
              <input type="date" value={startedAt} onChange={(e) => setStartedAt(e.target.value)} className={INPUT} />
            </label>
            <div className="flex justify-end"><Button disabled={!name.trim() || !startedAt} onClick={() => setStep(1)}>Next</Button></div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <label className="block text-sm font-medium text-slate-700">Cash in the bank and in hand today
              <input value={balance} inputMode="decimal" onChange={(e) => setBalance(e.target.value.replace(/[^0-9.-]/g, ""))} className={INPUT} />
            </label>
            <label className="block text-sm font-medium text-slate-700">Safety level
              <input value={threshold} inputMode="decimal" onChange={(e) => setThreshold(e.target.value.replace(/[^0-9.]/g, ""))} className={INPUT} />
              <span className="mt-1 block text-xs font-normal text-slate-500">You get a warning when your cash is forecast to fall below this. A good start is what you spend in two weeks.</span>
            </label>
            {error && <ErrorBox message={error} />}
            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(0)}>Back</Button>
              <Button disabled={busy} onClick={createBusiness}>{busy ? "Saving…" : "Next"}</Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">Add past sales and expenses so the forecast has something to learn from. Upload a CSV with date, amount and (optionally) type, category and description columns. You can skip this and add records later.</p>
            <div className="flex flex-wrap items-center gap-2">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                <Upload className="size-4" /> {busy ? "Importing…" : "Choose a CSV file"}
                <input type="file" accept=".csv,text/csv" className="hidden" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
              </label>
              <Button variant="ghost" onClick={downloadSample}><Download className="size-4" /> Sample CSV</Button>
            </div>
            {imported && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{imported}</p>}
            {error && <ErrorBox message={error} />}
            <div className="flex justify-end"><Button onClick={() => router.replace("/dashboard")}>{imported ? "Go to my dashboard" : "Skip for now"}</Button></div>
          </div>
        )}
      </Card>
    </div>
  );
}
