"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Gauge, LineChart, ShieldCheck, Wallet } from "lucide-react";
import { login } from "@/lib/api";
import { Button, ErrorBox } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password, code || undefined);
      router.replace("/dashboard");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      if (msg === "Two-factor code required") {
        setNeedCode(true);
        setError(null);
      } else setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const POINTS = [
    { icon: LineChart, text: "Cash shortage warnings up to 30 days ahead" },
    { icon: Gauge, text: "An explainable 300 to 900 credit score" },
    { icon: ShieldCheck, text: "You approve every payment, message and reminder" },
  ];
  const INPUT = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-emerald-500";
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-slate-200 p-12 lg:flex">
        <Link href="/" className="flex items-center gap-2">
          <span className="ff-glow flex size-9 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-300 text-white"><Wallet className="size-4" /></span>
          <span className="text-lg font-semibold tracking-tight">CashPilot</span>
        </Link>
        <div>
          <h2 className="ff-gradient-text text-4xl font-semibold leading-tight tracking-tight">Know your cash<br />before it runs out.</h2>
          <ul className="mt-8 space-y-4">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm text-slate-600">
                <span className="flex size-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200"><Icon className="size-4" /></span>{text}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-400">Estimates from your own data. Not financial advice.</p>
      </div>
      <div className="flex items-center justify-center px-4 py-10">
        <div className="ff-rise w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center text-center lg:hidden">
            <div className="ff-glow mb-3 flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-emerald-300 text-white"><Wallet className="size-5" /></div>
            <h1 className="text-2xl font-semibold tracking-tight">CashPilot</h1>
            <p className="mt-1 text-sm text-slate-500">Know your cash before it runs out.</p>
          </div>
          <h1 className="mb-1 hidden text-2xl font-semibold tracking-tight lg:block">Welcome back</h1>
          <p className="mb-6 hidden text-sm text-slate-500 lg:block">Sign in to your dashboard.</p>
          <form onSubmit={submit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Email</span>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Password</span>
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={INPUT} />
            </label>
            {needCode && (
              <label className="block">
                <span className="text-sm font-medium text-slate-700">Authenticator code</span>
                <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} required autoFocus value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="6-digit code"
                  className={`${INPUT} tracking-widest`} />
              </label>
            )}
            {error && <ErrorBox message={error} />}
            <Button type="submit" disabled={busy} className="w-full py-2.5">{busy ? "Signing in…" : "Sign in"}</Button>
            <p className="text-center text-sm text-slate-500">New here? <Link href="/signup" className="font-medium text-emerald-800 hover:underline">Create an account</Link></p>
          </form>
        </div>
      </div>
    </div>
  );
}
