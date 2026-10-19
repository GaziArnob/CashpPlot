"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { Bot, Compass, Gauge, Handshake, LineChart, Package, ShieldCheck, Wallet } from "lucide-react";
import Reveal from "@/components/Reveal";
import { getToken } from "@/lib/api";

const noopSubscribe = () => () => {};

const FEATURES = [
  { icon: LineChart, title: "Cash shortage warnings", text: "See your balance day by day for the next 30 days, and the exact day cash is forecast to run short, before it happens." },
  { icon: Compass, title: "A plan to fix it", text: "Collect from these customers, clear that stock, delay this bill. Every step shows the cash it brings, how soon, and the risk." },
  { icon: Handshake, title: "Supplier payment plans", text: "Spot payment clashes, propose a new schedule, draft the message to your supplier, and compare what financing would cost." },
  { icon: Package, title: "Product insights", text: "Which products to push, keep, shrink or clear, limited to what your cash can afford right now." },
  { icon: Gauge, title: "Explainable credit score", text: "A 300 to 900 score built from your own numbers, with the reasons behind it, and an estimate of what you could safely borrow." },
  { icon: Bot, title: "Ask in plain language", text: "“Will I run short next week?” The assistant answers using your real numbers, never made-up ones." },
];

const STEPS = [
  { n: "1", title: "Add your records", text: "Upload a CSV or enter sales, expenses, invoices and bills." },
  { n: "2", title: "See what's coming", text: "A 30-day forecast, ranked collections and a clear action plan." },
  { n: "3", title: "Decide with confidence", text: "Approve each step yourself. Nothing is paid, sent or applied for without you." },
];

export default function Landing() {
  const signedIn = useSyncExternalStore(noopSubscribe, () => !!getToken(), () => false);
  return (
    <div className="min-h-screen bg-white">
      <div className="sticky top-0 z-20 border-b border-slate-200 bg-[rgb(var(--ff-canvas)/0.75)] backdrop-blur"><header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-emerald-600 text-white"><Wallet className="size-4" /></span>
          <span className="text-lg font-semibold tracking-tight">CashPilot</span>
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          {signedIn ? (
            <Link href="/dashboard" className="ff-glow rounded-lg bg-emerald-600 px-3.5 py-2 font-medium text-white hover:bg-emerald-700">Open dashboard</Link>
          ) : (
            <>
              <Link href="/login" className="rounded-lg px-3 py-2 font-medium text-slate-700 hover:bg-slate-100">Sign in</Link>
              <Link href="/signup" className="ff-glow rounded-lg bg-emerald-600 px-3.5 py-2 font-medium text-white hover:bg-emerald-700">Get started</Link>
            </>
          )}
        </nav>
      </header></div>

      <section className="relative mx-auto max-w-4xl px-4 pb-16 pt-14 text-center sm:px-6 sm:pt-24">
        <div aria-hidden className="ff-orb pointer-events-none absolute left-1/2 top-10 -z-10 size-72 -translate-x-1/2 rounded-full bg-emerald-500/20 blur-3xl" />
        <p className="ff-rise mb-5 inline-block rounded-full bg-emerald-50 px-3.5 py-1 text-xs font-medium text-emerald-800 ring-1 ring-emerald-200">An AI financial assistant for small businesses</p>
        <h1 className="ff-rise ff-gradient-text text-5xl font-semibold tracking-tight sm:text-7xl" style={{ animationDelay: "80ms" }}>Profitable on paper.<br />Broke on payday?</h1>
        <p className="ff-rise mx-auto mt-6 max-w-2xl text-lg text-slate-600" style={{ animationDelay: "160ms" }}>CashPilot warns you about cash shortages 7 to 30 days before they happen, shows you who to chase and what to do about it, and tells you what you can safely borrow.</p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href={signedIn ? "/dashboard" : "/signup"} className="ff-glow rounded-lg bg-gradient-to-b from-emerald-500 to-emerald-600 px-6 py-3 text-sm font-semibold text-white transition hover:from-emerald-700 hover:to-emerald-700">{signedIn ? "Open dashboard" : "Start free"}</Link>
          {!signedIn && <Link href="/login" className="rounded-lg border border-slate-300 px-6 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100">Sign in</Link>}
        </div>
      </section>

      <section className="bg-slate-50 py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <Reveal><h2 className="text-center text-2xl font-semibold tracking-tight">Everything a small business owner needs to stay ahead of cash</h2></Reveal>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, text }, i) => (
              <Reveal key={title} delay={(i % 3) * 90} className="h-full">
              <div className="group h-full rounded-xl border border-slate-200 bg-white p-6 transition hover:-translate-y-1 hover:border-emerald-500/50">
                <span className="mb-4 flex size-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200 transition group-hover:bg-emerald-500 group-hover:text-white"><Icon className="size-5" /></span>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{text}</p>
              </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
        <h2 className="text-center text-2xl font-semibold tracking-tight">How it works</h2>
        <ol className="mt-10 grid gap-6 sm:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.n} className="text-center">
              <Reveal delay={i * 120}>
              <span className="mx-auto flex size-10 items-center justify-center rounded-full bg-emerald-600 text-sm font-semibold text-white">{s.n}</span>
              <h3 className="mt-3 font-semibold">{s.title}</h3>
              <p className="mt-1 text-sm text-slate-600">{s.text}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t border-slate-200 bg-slate-50 py-14">
        <Reveal className="mx-auto max-w-3xl"><div className="mx-auto flex flex-col items-center px-4 text-center sm:px-6">
          <ShieldCheck className="size-8 text-emerald-600" />
          <h2 className="mt-3 text-2xl font-semibold tracking-tight">Numbers you can trust, and you stay in control</h2>
          <p className="mt-3 text-slate-600">Every figure comes from testable calculations, not from an AI guessing. The AI only explains the results, and anything it says is checked against your data. Customer and supplier names are masked before any AI sees them. You approve every payment plan, message and reminder yourself.</p>
          <Link href={signedIn ? "/dashboard" : "/signup"} className="ff-glow mt-6 rounded-lg bg-gradient-to-b from-emerald-500 to-emerald-600 px-6 py-3 text-sm font-semibold text-white transition hover:from-emerald-700 hover:to-emerald-700">{signedIn ? "Open dashboard" : "Create your free account"}</Link>
        </div></Reveal>
      </section>

      <section className="mx-auto max-w-4xl px-4 py-16 sm:px-6">
        <h2 className="text-center text-2xl font-semibold tracking-tight">Start free, upgrade when you need more</h2>
        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 p-6">
            <h3 className="font-semibold">Free</h3>
            <p className="mt-1.5 text-sm text-slate-600">Transactions, customers, invoices, the dashboard and a 7-day cash forecast.</p>
          </div>
          <div className="rounded-xl border-2 border-emerald-600 p-6">
            <h3 className="font-semibold">Pro <span className="text-xs font-normal text-emerald-700">14-day free trial</span></h3>
            <p className="mt-1.5 text-sm text-slate-600">The 30-day forecast, Cash Advisor, collections, supplier plans, credit score, loans, reports and the AI assistant.</p>
          </div>
        </div>
        <p className="mt-4 text-center text-xs text-slate-500">Billing is in demo mode: switching plans takes no payment.</p>
      </section>

      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-500">
        <p>CashPilot gives estimates from your own data. It is not financial advice, and loan figures are not an approval.</p>
        <p className="mt-2">Are you a lender? <Link href="/lender" className="font-medium text-emerald-800 hover:underline">Open a shared business view</Link></p>
      </footer>
    </div>
  );
}
