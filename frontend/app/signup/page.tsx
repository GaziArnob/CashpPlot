"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Wallet } from "lucide-react";
import { Button, ErrorBox } from "@/components/ui";
import { api, setToken } from "@/lib/api";

const INPUT = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) return setError("Use at least 8 characters for your password.");
    if (password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    try {
      const r = await api<{ access_token: string }>("/auth/signup", { method: "POST", body: JSON.stringify({ name, email, password }) });
      setToken(r.access_token);
      router.replace("/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the account");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Link href="/" className="mb-3 flex size-11 items-center justify-center rounded-xl bg-emerald-600 text-white"><Wallet className="size-5" /></Link>
          <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
          <p className="mt-1 text-sm text-slate-500">Free to start. No card needed.</p>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6">
          <label className="block text-sm font-medium text-slate-700">Your name
            <input required value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={INPUT} autoComplete="name" />
          </label>
          <label className="block text-sm font-medium text-slate-700">Work email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} autoComplete="email" />
          </label>
          <label className="block text-sm font-medium text-slate-700">Password
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={INPUT} autoComplete="new-password" />
          </label>
          <label className="block text-sm font-medium text-slate-700">Confirm password
            <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={INPUT} autoComplete="new-password" />
          </label>
          {error && <ErrorBox message={error} />}
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Creating…" : "Create account"}</Button>
          <p className="text-center text-sm text-slate-500">Already have an account? <Link href="/login" className="font-medium text-emerald-700 hover:underline">Sign in</Link></p>
        </form>
      </div>
    </div>
  );
}
