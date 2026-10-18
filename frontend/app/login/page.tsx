"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Wallet } from "lucide-react";
import { login } from "@/lib/api";
import { Button, ErrorBox } from "@/components/ui";

const DEMO = { email: "demo@example.com", password: "Demo@12345" }; // from backend/seed/seed.py

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-3 flex size-11 items-center justify-center rounded-xl bg-emerald-600 text-white">
            <Wallet className="size-5" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">CashPilot</h1>
          <p className="mt-1 text-sm text-slate-500">Know your cash before it runs out.</p>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Email</span>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Password</span>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" />
          </label>
          {error && <ErrorBox message={error} />}
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Signing in…" : "Sign in"}</Button>
          <button type="button" onClick={() => { setEmail(DEMO.email); setPassword(DEMO.password); }}
            className="w-full text-center text-sm text-emerald-700 hover:underline">
            Fill in the demo account
          </button>
        </form>
      </div>
    </div>
  );
}
