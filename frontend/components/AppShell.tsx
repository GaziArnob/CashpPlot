"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";
import {
  Bot, Compass, Gauge, Handshake, Landmark, LayoutDashboard, LineChart, LogOut, NotebookTabs, Package, Wallet,
} from "lucide-react";
import { getToken, logout } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/advisor", label: "Cash Advisor", icon: Compass },
  { href: "/cashflow", label: "Cash Flow", icon: LineChart },
  { href: "/ledger", label: "Ledger", icon: NotebookTabs },
  { href: "/payables", label: "Supplier Plans", icon: Handshake },
  { href: "/products", label: "Products", icon: Package },
  { href: "/credit-score", label: "Credit Score", icon: Gauge },
  { href: "/loan", label: "Loan Center", icon: Landmark },
  { href: "/agent", label: "AI Agent", icon: Bot },
];

const noopSubscribe = () => () => {};

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  // undefined on the server, the stored token (or null) in the browser
  const token = useSyncExternalStore(noopSubscribe, getToken, () => undefined);

  useEffect(() => {
    if (token === null) router.replace("/login");
  }, [token, router]);

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  if (!token) return null;

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-600 text-white">
            <Wallet className="size-4" />
          </div>
          <span className="text-lg font-semibold tracking-tight">CashPilot</span>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link key={href} href={href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active ? "bg-emerald-50 text-emerald-700" : "text-slate-600 hover:bg-slate-100"}`}>
                <Icon className="size-4" /> {label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <button onClick={signOut}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">
            <LogOut className="size-4" /> Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white md:hidden">
          <div className="flex items-center justify-between px-4 py-3">
            <span className="font-semibold">CashPilot</span>
            <button onClick={signOut} className="text-slate-500" aria-label="Sign out"><LogOut className="size-4" /></button>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-2">
            {NAV.map(({ href, label }) => (
              <Link key={href} href={href}
                className={`whitespace-nowrap rounded-full px-3 py-1 text-xs font-medium ${
                  pathname.startsWith(href) ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600"}`}>
                {label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}
