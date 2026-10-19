"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Check, Download, Factory, FileSpreadsheet, Shapes, ShoppingBag, UploadCloud, UtensilsCrossed, Warehouse, Wrench, type LucideIcon } from "lucide-react";
import { Button, Card, ErrorBox } from "@/components/ui";
import { api, getToken } from "@/lib/api";

const INPUT = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-emerald-500";
const TYPES: { label: string; icon: LucideIcon }[] = [
  { label: "Retail", icon: ShoppingBag },
  { label: "Wholesale", icon: Warehouse },
  { label: "Restaurant & food", icon: UtensilsCrossed },
  { label: "Services", icon: Wrench },
  { label: "Manufacturing", icon: Factory },
  { label: "Other", icon: Shapes },
];
const CURRENCIES: { code: string; symbol: string; label?: string }[] = [
  { code: "USD", symbol: "$" }, { code: "CNY", symbol: "¥", label: "RMB" }, { code: "EUR", symbol: "€" }, { code: "GBP", symbol: "£" }, { code: "CAD", symbol: "C$" },
  { code: "AUD", symbol: "A$" }, { code: "SGD", symbol: "S$" }, { code: "INR", symbol: "₹" },
];
// how long the business has been running, as the number of days back its start date is set
const AGES = [
  { label: "Just starting", hint: "This month", days: 0 },
  { label: "Under a year", hint: "A few months", days: 180 },
  { label: "1 to 3 years", hint: "Up and running", days: 730 },
  { label: "3+ years", hint: "Well established", days: 1825 },
];
const STEPS = [
  { title: "Your business", sub: "Tell us a little about it" },
  { title: "Your cash", sub: "Where you stand today" },
  { title: "Your records", sub: "Optional, but it helps" },
];
const SAMPLE_CSV = "date,amount,type,category,description\n2026-01-05,1200,income,Sales,Weekend sales\n2026-01-06,-450,expense,Inventory,Stock purchase\n2026-01-07,-90,expense,Utilities,Electricity\n";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [type, setType] = useState(TYPES[0].label);
  const [currency, setCurrency] = useState("USD");
  const [age, setAge] = useState(2);
  const [balance, setBalance] = useState("");
  const [threshold, setThreshold] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const symbol = CURRENCIES.find((c) => c.code === currency)?.symbol ?? "";
  const cash = Number(balance) || 0;
  const money = (n: number) => `${symbol}${Math.round(n).toLocaleString("en-US")}`;
  const SAFETY_PRESETS = [
    { label: "No warning level", value: 0 },
    { label: "10% of my cash", value: Math.round(cash * 0.1) },
    { label: "25% of my cash", value: Math.round(cash * 0.25) },
  ];

  async function createBusiness() {
    setBusy(true);
    setError(null);
    try {
      const started = new Date(Date.now() - AGES[age].days * 86400000).toISOString().slice(0, 10);
      await api("/onboarding", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), type, currency, started_at: started, opening_balance: cash, cash_threshold: Number(threshold) || 0 }),
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

  function next(e: FormEvent) {
    e.preventDefault();
    if (step === 0 && name.trim()) setStep(1);
    else if (step === 1 && !busy) createBusiness();
  }

  const percent = ((step + (step === 2 && imported ? 1 : 0.5)) / STEPS.length) * 100;

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-4 py-10">
      <div className="ff-rise">
        <p className="text-xs font-medium uppercase tracking-wider text-emerald-800">Welcome to CashPilot</p>
        <h1 className="ff-gradient-text mt-1 text-3xl font-semibold tracking-tight">Let&apos;s set up your business</h1>
        <p className="mt-1 text-sm text-slate-500">Takes about a minute. Every answer can be changed later in Settings.</p>
      </div>

      <div className="my-6">
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-300 transition-all duration-700" style={{ width: `${percent}%` }} />
        </div>
        <ol className="mt-3 grid grid-cols-3 gap-2">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex items-center gap-2">
              <span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold transition ${i < step ? "bg-emerald-600 text-white" : i === step ? "border-2 border-emerald-500 text-emerald-800" : "bg-slate-100 text-slate-400"}`}>
                {i < step ? <Check className="size-3.5" /> : i + 1}
              </span>
              <span className="min-w-0">
                <span className={`block truncate text-xs ${i === step ? "font-semibold text-slate-900" : "text-slate-500"}`}>{s.title}</span>
                <span className="hidden truncate text-[11px] text-slate-400 sm:block">{s.sub}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>

      <Card key={step} className="ff-pop">
        {step === 0 && (
          <form onSubmit={next} className="space-y-6">
            <label className="block text-sm font-medium text-slate-700">What is your business called?
              <input value={name} maxLength={160} autoFocus onChange={(e) => setName(e.target.value)} className={INPUT} placeholder="e.g. Evergreen Traders" />
            </label>

            <fieldset>
              <legend className="text-sm font-medium text-slate-700">What kind of business is it?</legend>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {TYPES.map(({ label, icon: Icon }) => (
                  <button key={label} type="button" onClick={() => setType(label)} aria-pressed={type === label}
                    className={`flex flex-col items-center gap-1.5 rounded-xl border px-2 py-3 text-xs font-medium transition ${type === label ? "border-emerald-500 bg-emerald-50 text-emerald-800 ff-glow" : "border-slate-300 text-slate-600 hover:border-slate-400 hover:bg-slate-100"}`}>
                    <Icon className="size-5" /> {label}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="text-sm font-medium text-slate-700">Which currency do you work in?</legend>
              <div className="mt-2 flex flex-wrap gap-2">
                {CURRENCIES.map((c) => (
                  <button key={c.code} type="button" onClick={() => setCurrency(c.code)} aria-pressed={currency === c.code}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${currency === c.code ? "border-emerald-500 bg-emerald-50 text-emerald-800" : "border-slate-300 text-slate-600 hover:bg-slate-100"}`}>
                    {c.symbol} {c.label ?? c.code}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="text-sm font-medium text-slate-700">How long have you been running it?</legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {AGES.map((a, i) => (
                  <button key={a.label} type="button" onClick={() => setAge(i)} aria-pressed={age === i}
                    className={`rounded-xl border px-3 py-2.5 text-left transition ${age === i ? "border-emerald-500 bg-emerald-50" : "border-slate-300 hover:bg-slate-100"}`}>
                    <span className={`block text-sm font-medium ${age === i ? "text-emerald-800" : "text-slate-700"}`}>{a.label}</span>
                    <span className="block text-xs text-slate-500">{a.hint}</span>
                  </button>
                ))}
              </div>
            </fieldset>

            <div className="flex justify-end"><Button type="submit" disabled={!name.trim()}>Next <ArrowRight className="size-4" /></Button></div>
          </form>
        )}

        {step === 1 && (
          <form onSubmit={next} className="space-y-6">
            <label className="block text-sm font-medium text-slate-700">How much cash do you have today?
              <span className="mt-0.5 block text-xs font-normal text-slate-500">Bank balance plus cash in hand. A rough number is fine.</span>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-500">{symbol}</span>
                <input value={balance} inputMode="decimal" autoFocus placeholder="0" style={{ paddingLeft: `${12 + symbol.length * 9 + 8}px` }}
                  onChange={(e) => setBalance(e.target.value.replace(/[^0-9.-]/g, ""))} className={`${INPUT} text-base tabular`} />
              </div>
            </label>

            <div>
              <label className="block text-sm font-medium text-slate-700">Warn me when my cash might drop below…
                <span className="mt-0.5 block text-xs font-normal text-slate-500">Your safety cushion. A good start is what you spend in about two weeks. Not sure? Pick one below and change it any time.</span>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-500">{symbol}</span>
                  <input value={threshold} inputMode="decimal" placeholder="0" style={{ paddingLeft: `${12 + symbol.length * 9 + 8}px` }}
                    onChange={(e) => setThreshold(e.target.value.replace(/[^0-9.]/g, ""))} className={`${INPUT} text-base tabular`} />
                </div>
              </label>
              <div className="mt-2 flex flex-wrap gap-2">
                {SAFETY_PRESETS.map((p) => (
                  <button key={p.label} type="button" onClick={() => setThreshold(String(p.value))}
                    className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-emerald-500 hover:bg-emerald-50 hover:text-emerald-800">
                    {p.label}{p.value > 0 ? ` (${money(p.value)})` : ""}
                  </button>
                ))}
              </div>
            </div>

            {error && <ErrorBox message={error} />}
            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(0)}><ArrowLeft className="size-4" /> Back</Button>
              <Button type="submit" disabled={busy}>{busy ? "Saving…" : <>Next <ArrowRight className="size-4" /></>}</Button>
            </div>
          </form>
        )}

        {step === 2 && (
          <div className="space-y-5">
            <div>
              <h2 className="text-base font-semibold">Your business is ready</h2>
              <p className="mt-1 text-sm text-slate-600">Past sales and expenses help the forecast learn your patterns. Add them now from a spreadsheet, or skip and enter them later.</p>
            </div>

            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) upload(f); }}
              onClick={() => fileInput.current?.click()}
              role="button" tabIndex={0}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileInput.current?.click(); }}
              className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition ${dragging ? "border-emerald-500 bg-emerald-50" : "border-slate-300 hover:border-emerald-500/60 hover:bg-slate-100"}`}>
              {imported ? <Check className="size-8 text-emerald-600" /> : <UploadCloud className={`size-8 text-emerald-800 ${busy ? "animate-pulse" : ""}`} />}
              <p className="text-sm font-medium text-slate-800">{busy ? "Importing…" : imported ? "Done. You can add another file." : "Drop a CSV file here, or click to choose"}</p>
              <p className="flex items-center gap-1 text-xs text-slate-500"><FileSpreadsheet className="size-3.5" /> Columns: date, amount, and optionally type, category, description</p>
              <input ref={fileInput} type="file" accept=".csv,text/csv" className="hidden" disabled={busy}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            </div>

            <div className="flex items-center justify-between">
              <Button variant="ghost" onClick={downloadSample}><Download className="size-4" /> Get a sample CSV</Button>
            </div>
            {imported && <p className="ff-pop rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{imported}</p>}
            {error && <ErrorBox message={error} />}

            <div className="flex items-center justify-between border-t border-slate-200 pt-4">
              <span className="text-xs text-slate-500">{imported ? "All set." : "No file? No problem."}</span>
              <Button onClick={() => router.replace("/dashboard")}>{imported ? "Go to my dashboard" : "Skip, I'll add them later"} <ArrowRight className="size-4" /></Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
