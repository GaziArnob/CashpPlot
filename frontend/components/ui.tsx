"use client";

import { Loader2, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`ff-rise rounded-xl border border-slate-200 bg-white p-5 ${className}`}>{children}</div>;
}

export function CardTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold text-slate-700">{children}</h2>
      {right}
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="ff-gradient-text text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

/** Counts the first number in a text up from zero ("$65,000" -> "$0" ... "$65,000"). Other values show as they are. */
function CountUp({ value }: { value: ReactNode }) {
  const text = typeof value === "string" ? value : typeof value === "number" ? String(value) : null;
  const match = text?.match(/^(\D*?)(-?\d[\d,]*)(\.\d+)?(.*)$/);
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    if (!match || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / 900);
      setProgress(1 - Math.pow(1 - p, 3));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [text]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!match || !text) return <>{value}</>;
  const [, prefix, whole, decimals = "", suffix] = match;
  if (progress >= 1 || typeof window === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return <>{text}</>;
  const target = Number(whole.replace(/,/g, ""));
  const shown = Math.round(target * progress);
  const formatted = whole.includes(",") ? shown.toLocaleString("en-US") : String(shown);
  return <>{prefix}{formatted}{decimals}{suffix}</>;
}

export function Stat({ label, value, hint, tone = "default" }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: "default" | "good" | "bad" | "warn";
}) {
  const color = { default: "text-slate-900", good: "text-emerald-600", bad: "text-rose-600", warn: "text-amber-600" }[tone];
  return (
    <Card className="relative overflow-hidden">
      <span aria-hidden className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-emerald-300/60 to-transparent" />
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular ${color}`}><CountUp value={value} /></p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
}

const BADGE = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  red: "bg-rose-50 text-rose-700 ring-rose-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
};

export function Badge({ children, color = "slate" }: { children: ReactNode; color?: keyof typeof BADGE }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${BADGE[color]}`}>
      {children}
    </span>
  );
}

export function Button({ children, onClick, variant = "primary", disabled, type = "button", className = "" }: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean; type?: "button" | "submit"; className?: string;
}) {
  const styles = {
    primary: "ff-sheen bg-gradient-to-b from-emerald-500 to-emerald-600 text-white shadow-[0_6px_18px_-6px_rgb(91_91_214/0.7)] hover:from-emerald-700 hover:to-emerald-700 active:scale-[0.98] disabled:opacity-50 disabled:shadow-none",
    secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400",
    ghost: "text-slate-600 hover:bg-slate-100",
  }[variant];
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-all ${styles} ${className}`}>
      {children}
    </button>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="space-y-4 py-8" role="status" aria-label={`${label}…`}>
      <div className="flex items-center justify-center gap-2 text-sm text-slate-500"><Loader2 className="size-4 animate-spin" /> {label}…</div>
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => <div key={i} className="ff-skeleton h-20 rounded-xl" />)}
      </div>
      <div className="ff-skeleton h-40 rounded-xl" />
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div className="flex-1">
        {message}
        {message.startsWith("Upgrade to Pro") && (
          <> <Link href="/settings#plan" className="font-medium underline">See plans</Link></>
        )}
      </div>
      {onRetry && <button className="font-medium underline" onClick={onRetry}>Retry</button>}
    </div>
  );
}
