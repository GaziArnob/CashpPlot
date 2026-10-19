"use client";

import { useState } from "react";
import { Landmark, RefreshCw, Unplug } from "lucide-react";
import { Button, Card, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Status = {
  configured: boolean; environment: string;
  connections: { id: number; institution: string; last_synced_at: string | null }[];
};

type PlaidHandler = { open: () => void };
type PlaidGlobal = {
  create: (cfg: { token: string; onSuccess: (publicToken: string, meta: { institution?: { name?: string } }) => void; onExit?: () => void }) => PlaidHandler;
};

function loadPlaid(): Promise<PlaidGlobal> {
  const w = window as unknown as { Plaid?: PlaidGlobal };
  if (w.Plaid) return Promise.resolve(w.Plaid);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
    s.onload = () => (w.Plaid ? resolve(w.Plaid) : reject(new Error("Bank connection could not load")));
    s.onerror = () => reject(new Error("Bank connection could not load"));
    document.head.appendChild(s);
  });
}

/** Link a bank (Plaid) and import its transactions. Hidden for staff and on the free plan. */
export default function BankPanel({ onSynced }: { onSynced: () => void }) {
  const status = useApi<Status>("/bank/status");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  if (!status.data) {
    // Free plan: show the upgrade notice. Staff and other errors: show nothing.
    return status.error?.startsWith("Upgrade to Pro") ? <div className="mb-6"><ErrorBox message={status.error} /></div> : null;
  }
  const s = status.data;

  async function run<T>(label: string, fn: () => Promise<T>, done?: (r: T) => string) {
    setBusy(label);
    setError(null);
    setNote(null);
    try {
      const r = await fn();
      if (done) setNote(done(r));
      status.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  }

  const connect = () => run("connect", async () => {
    const { link_token } = await api<{ link_token: string }>("/bank/link-token", { method: "POST" });
    const Plaid = await loadPlaid();
    await new Promise<void>((resolve) => {
      Plaid.create({
        token: link_token,
        onExit: () => resolve(),
        onSuccess: async (publicToken, meta) => {
          try {
            await api("/bank/exchange", { method: "POST", body: JSON.stringify({ public_token: publicToken, institution_name: meta.institution?.name ?? "Bank" }) });
            setNote("Bank connected. Press Sync to import its transactions.");
          } catch (e) {
            setError(e instanceof Error ? e.message : "Could not save the connection");
          }
          resolve();
        },
      }).open();
    });
  });

  return (
    <Card className="mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <Landmark className="mt-0.5 size-5 text-emerald-700" />
          <div>
            <p className="font-medium">Bank connection</p>
            <p className="text-xs text-slate-500">
              {s.configured
                ? `Import transactions straight from your bank. Nothing is imported until you press Sync.${s.environment === "sandbox" ? " Test mode: sample banks only." : ""}`
                : "Not set up yet. Add the bank connection keys on the server to turn this on."}
            </p>
          </div>
        </div>
        {s.configured && <Button variant="secondary" disabled={busy !== null} onClick={connect}>{busy === "connect" ? "Opening…" : "Connect a bank"}</Button>}
      </div>
      {s.connections.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
          {s.connections.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
              <span><span className="font-medium">{c.institution}</span> <span className="text-slate-500">{c.last_synced_at ? `last synced ${c.last_synced_at.slice(0, 10)}` : "not synced yet"}</span></span>
              <span className="flex gap-1">
                <Button variant="ghost" disabled={busy !== null} onClick={() => run(`sync${c.id}`, () => api<{ imported: number; skipped: number; removed: number }>(`/bank/${c.id}/sync`, { method: "POST" }), (r) => { onSynced(); return `Imported ${r.imported} transaction${r.imported === 1 ? "" : "s"}${r.skipped ? `, skipped ${r.skipped} (pending or another currency)` : ""}.`; })}>
                  <RefreshCw className="size-4" />{busy === `sync${c.id}` ? "Syncing…" : "Sync"}
                </Button>
                <Button variant="ghost" disabled={busy !== null} onClick={() => window.confirm(`Disconnect ${c.institution}? Transactions already imported stay.`) && run(`del${c.id}`, () => api(`/bank/${c.id}`, { method: "DELETE" }))}>
                  <Unplug className="size-4" />Disconnect
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {note && <p className="mt-3 text-sm text-emerald-700">{note}</p>}
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
    </Card>
  );
}
