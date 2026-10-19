"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";
import {
  Bell, Bot, Compass, FileBarChart, Gauge, Handshake, Landmark, LayoutDashboard, LineChart, LogOut, NotebookTabs,
  Package, Receipt, Settings, Users, Wallet, type LucideIcon,
} from "lucide-react";
import UnreadBadge from "@/components/UnreadBadge";
import { getToken, logout } from "@/lib/api";
import { useMe } from "@/lib/hooks";

type Item = { href: string; label: string; icon: LucideIcon };

const GROUPS: { title: string; items: Item[] }[] = [
  { title: "Overview", items: [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/advisor", label: "Cash Advisor", icon: Compass },
    { href: "/notifications", label: "Notifications", icon: Bell },
  ] },
  { title: "Money", items: [
    { href: "/transactions", label: "Transactions", icon: Receipt },
    { href: "/cashflow", label: "Cash Flow", icon: LineChart },
    { href: "/ledger", label: "Ledger", icon: NotebookTabs },
    { href: "/customers", label: "Customers", icon: Users },
    { href: "/payables", label: "Supplier Plans", icon: Handshake },
    { href: "/products", label: "Products", icon: Package },
  ] },
  { title: "Finance", items: [
    { href: "/credit-score", label: "Credit Score", icon: Gauge },
    { href: "/loan", label: "Loan Center", icon: Landmark },
    { href: "/reports", label: "Reports", icon: FileBarChart },
  ] },
  { title: "Assistant", items: [{ href: "/agent", label: "AI Agent", icon: Bot }] },
];
const SETTINGS: Item = { href: "/settings", label: "Settings", icon: Settings };
const ALL = [...GROUPS.flatMap((g) => g.items), SETTINGS];

const STAFF_PAGES = ["/transactions", "/ledger", "/customers"];

const noopSubscribe = () => () => {};

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  // undefined on the server, the stored token (or null) in the browser
  const token = useSyncExternalStore(noopSubscribe, getToken, () => undefined);

  const me = useMe();
  const staff = me?.role === "staff";

  useEffect(() => {
    if (token === null) router.replace("/login");
  }, [token, router]);

  useEffect(() => {
    if (staff && !STAFF_PAGES.some((p) => pathname.startsWith(p))) router.replace("/transactions");
  }, [staff, pathname, router]);

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  if (!token) return null;
  const groups = staff
    ? GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => STAFF_PAGES.includes(i.href)) })).filter((g) => g.items.length)
    : GROUPS;
  const mobile = staff ? groups.flatMap((g) => g.items) : ALL;
  const link = ({ href, label, icon: Icon }: Item) => (
    <Link key={href} href={href}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
        pathname.startsWith(href) ? "bg-emerald-50 text-emerald-800 shadow-[inset_2px_0_0_rgb(91_91_214)]" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}>
      <Icon className="size-4" /> {label}
      {href === "/notifications" && !staff && <UnreadBadge />}
    </Link>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-[rgb(var(--ff-surface)/0.8)] backdrop-blur md:flex">
        <Link href="/" className="flex items-center gap-2 px-5 py-5">
          <div className="ff-glow flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-300 text-white"><Wallet className="size-4" /></div>
          <span className="text-lg font-semibold tracking-tight">CashPilot</span>
        </Link>
        <nav className="flex-1 space-y-4 overflow-y-auto px-3 pb-3">
          {groups.map((g) => (
            <div key={g.title}>
              <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{g.title}</p>
              <div className="space-y-0.5">{g.items.map(link)}</div>
            </div>
          ))}
        </nav>
        <div className="space-y-0.5 border-t border-slate-200 p-3">
          {!staff && link(SETTINGS)}
          <button onClick={signOut}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">
            <LogOut className="size-4" /> Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-[rgb(var(--ff-surface)/0.8)] backdrop-blur md:hidden">
          <div className="flex items-center justify-between px-4 py-3">
            <span className="font-semibold">CashPilot</span>
            <button onClick={signOut} className="text-slate-500" aria-label="Sign out"><LogOut className="size-4" /></button>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-2">
            {mobile.map(({ href, label }) => (
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
