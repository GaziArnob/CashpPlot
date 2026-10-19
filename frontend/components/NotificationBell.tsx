"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export type Alert = {
  id: number; type: string; label: string; message: string; severity: "info" | "warning" | "critical";
  link: string | null; is_read: boolean; created_at: string;
};

export const SEVERITY = {
  critical: { dot: "bg-rose-500", badge: "red", text: "Urgent" },
  warning: { dot: "bg-amber-500", badge: "amber", text: "Heads up" },
  info: { dot: "bg-sky-500", badge: "blue", text: "Info" },
} as const;

/** The database stores UTC without a zone, so mark it as UTC before showing it in the reader's time. */
export function when(iso: string) {
  return new Date(iso + "Z").toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

const POLL_MS = 60_000;

/** A bell with the unread count; opens the latest alerts. Refreshes every minute. */
export default function NotificationBell() {
  const router = useRouter();
  // The page in the query makes it refetch on every navigation, so alerts raised by a page load show at once.
  const page = usePathname();
  const { data, reload } = useApi<{ unread: number; total: number; latest: Alert[] }>(`/notifications/summary?page=${encodeURIComponent(page)}`);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const id = window.setInterval(reload, POLL_MS);
    return () => window.clearInterval(id);
  }, [reload]);

  async function openAlert(n: Alert) {
    setOpen(false);
    if (!n.is_read) {
      try { await api(`/notifications/${n.id}/read`, { method: "PATCH" }); } catch { /* the link still works */ }
      reload();
    }
    if (n.link) router.push(n.link);
  }

  async function readAll() {
    try { await api("/notifications/read-all", { method: "POST" }); } catch { /* ignore: the list refreshes below */ }
    reload();
  }

  const unread = data?.unread ?? 0;
  const total = data?.total ?? 0;
  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)} aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="relative flex size-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100">
        <Bell className="size-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-rose-600 px-1 text-[10px] font-semibold leading-4 text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <button aria-label="Close notifications" className="fixed inset-0 z-30 cursor-default" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-40 mt-2 w-80 max-w-[85vw] rounded-xl border border-slate-200 bg-white shadow-lg">
            <div className="border-b border-slate-100 px-4 py-3">
              <div className="flex items-baseline justify-between">
                <p className="text-sm font-semibold">Notifications</p>
                <p className="text-xs text-slate-500">{unread} unread · {total} in all</p>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Link href="/notifications" onClick={() => setOpen(false)}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-center text-sm font-medium text-white hover:bg-emerald-700">
                  View all
                </Link>
                <button onClick={readAll} disabled={unread === 0}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent">
                  Mark all read
                </button>
              </div>
            </div>
            <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
              {(data?.latest ?? []).length === 0 && <li className="px-4 py-6 text-center text-sm text-slate-500">Nothing needs your attention.</li>}
              {(data?.latest ?? []).map((n) => (
                <li key={n.id}>
                  <button onClick={() => openAlert(n)} className={`flex w-full gap-3 px-4 py-3 text-left hover:bg-slate-50 ${n.is_read ? "" : "bg-emerald-50/40"}`}>
                    <span className={`mt-1.5 size-2 shrink-0 rounded-full ${n.is_read ? "bg-slate-300" : SEVERITY[n.severity].dot}`} />
                    <span className="min-w-0">
                      <span className={`block text-sm ${n.is_read ? "text-slate-600" : "font-medium text-slate-900"}`}>{n.message}</span>
                      <span className="mt-0.5 block text-xs text-slate-500">{n.label} · {when(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {total > (data?.latest.length ?? 0) && (
              <p className="border-t border-slate-100 px-4 py-2 text-center text-xs text-slate-500">
                Showing the latest {data?.latest.length} of {total}. Use “View all” to see every notification.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
