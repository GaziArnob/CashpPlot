"use client";

import Link from "next/link";
import { useState } from "react";
import { Bell, Check, X } from "lucide-react";
import { SEVERITY, when, type Alert } from "@/lib/alerts";
import { Badge, Button, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function NotificationsPage() {
  const [tab, setTab] = useState<"all" | "unread">("all");
  const { data, error, loading, reload } = useApi<{ total: number; items: Alert[] }>(`/notifications?limit=100${tab === "unread" ? "&unread_only=true" : ""}`);
  const [err, setErr] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>) {
    setErr(null);
    try { await fn(); reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong"); }
  }

  return (
    <>
      <PageHeader title="Notifications" subtitle="Things that need your attention, each shown once"
        right={
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5">
              {(["all", "unread"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${tab === t ? "bg-emerald-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>
                  {t === "all" ? "All" : "Unread"}
                </button>
              ))}
            </div>
            <Button variant="secondary" onClick={() => act(() => api("/notifications/read-all", { method: "POST" }))}><Check className="size-4" /> Mark all read</Button>
            <Link href="/settings#notifications" className="text-sm font-medium text-emerald-700 hover:underline">Choose what you get</Link>
          </div>
        } />
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      {loading && !data ? <Loading /> : error || !data ? <ErrorBox message={error ?? "No data"} onRetry={reload} /> : data.items.length === 0 ? (
        <Card className="flex flex-col items-center py-12 text-center">
          <Bell className="size-8 text-slate-300" />
          <p className="mt-3 font-medium">{tab === "unread" ? "You are all caught up" : "No notifications yet"}</p>
          <p className="mt-1 max-w-sm text-sm text-slate-500">Alerts appear here when cash is forecast to run short, a customer is far behind, or a bill, invoice or loan installment is coming due.</p>
        </Card>
      ) : (
        <Card className="p-0">
          <ul className="divide-y divide-slate-100">
            {data.items.map((n) => (
              <li key={n.id} className={`flex flex-wrap items-start gap-3 px-5 py-4 ${n.is_read ? "" : "bg-emerald-50/40"}`}>
                <span className={`mt-2 size-2 shrink-0 rounded-full ${n.is_read ? "bg-slate-300" : SEVERITY[n.severity].dot}`} />
                <div className="min-w-0 flex-1">
                  <p className={`text-sm ${n.is_read ? "text-slate-600" : "font-medium text-slate-900"}`}>{n.message}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <Badge color={SEVERITY[n.severity].badge}>{SEVERITY[n.severity].text}</Badge>
                    <span>{n.label}</span><span>·</span><span>{when(n.created_at)}</span>
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  {n.link && (
                    <Link href={n.link} onClick={() => !n.is_read && act(() => api(`/notifications/${n.id}/read`, { method: "PATCH" }))}
                      className="rounded-lg px-2.5 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-50">Open</Link>
                  )}
                  {!n.is_read && <Button variant="ghost" className="px-2.5" onClick={() => act(() => api(`/notifications/${n.id}/read`, { method: "PATCH" }))}>Mark read</Button>}
                  <button aria-label="Dismiss" onClick={() => act(() => api(`/notifications/${n.id}`, { method: "DELETE" }))}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"><X className="size-4" /></button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
