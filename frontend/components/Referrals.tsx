"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import { Badge, Button, Card, CardTitle, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { LoanOption } from "@/lib/types";

type Referral = {
  id: number; lender_name: string; product_name: string; requested_amount: number; score_snapshot: number;
  shared_fields: string[]; status: "submitted" | "contacted" | "funded" | "declined" | "withdrawn"; consent_at: string;
};
type Listing = { items: Referral[]; summary: { total: number; by_status: Record<string, number> }; disclaimer: string };

const SHARE = [["credit_score", "Credit score"], ["pnl", "Profit & loss"], ["cash_forecast", "Cash forecast"]] as const;
const COLOR = { submitted: "blue", contacted: "amber", funded: "green", declined: "red", withdrawn: "slate" } as const;
const NEXT: Record<string, [string, string][]> = {
  submitted: [["contacted", "Lender contacted me"], ["declined", "Declined"], ["withdrawn", "Withdraw"]],
  contacted: [["funded", "Funded"], ["declined", "Declined"], ["withdrawn", "Withdraw"]],
};

export function IntroduceModal({ option, onClose, onDone }: { option: LoanOption; onClose: () => void; onDone: () => void }) {
  const [share, setShare] = useState<string[]>(["credit_score", "pnl"]);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function send() {
    setBusy(true);
    setError(null);
    try {
      await api("/referrals", { method: "POST", body: JSON.stringify({ loan_product_id: option.product_id, amount: option.recommended_amount, share, confirm: true }) });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the request");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Request an introduction" subtitle={`${option.name} · ${option.lender} · ${money(option.recommended_amount)}`} onClose={onClose}>
      <p className="mb-3 text-sm text-slate-600">This records that you would like to be introduced. Nothing is sent to the lender automatically, and it is not a loan application.</p>
      <p className="mb-1 text-sm font-medium">Information you agree to share</p>
      <div className="mb-3 space-y-1 text-sm">
        {SHARE.map(([v, l]) => (
          <label key={v} className="flex items-center gap-2">
            <input type="checkbox" checked={share.includes(v)} onChange={(e) => setShare(e.target.checked ? [...share, v] : share.filter((s) => s !== v))} /> {l}
          </label>
        ))}
      </div>
      <label className="mb-4 flex items-start gap-2 text-sm text-slate-600">
        <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> I consent to sharing the selected information with this lender.
      </label>
      {error && <div className="mb-3"><ErrorBox message={error} /></div>}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button disabled={!consent || share.length === 0 || busy} onClick={send}>{busy ? "Saving…" : "Save request"}</Button>
      </div>
    </Modal>
  );
}

export function ReferralsCard({ refreshKey }: { refreshKey: number }) {
  const { data, error, reload } = useApi<Listing>(`/referrals?k=${refreshKey}`);
  const [err, setErr] = useState<string | null>(null);
  async function mark(id: number, status: string) {
    setErr(null);
    try {
      await api(`/referrals/${id}/status`, { method: "POST", body: JSON.stringify({ status }) });
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update");
    }
  }
  if (error) return <ErrorBox message={error} />;
  if (!data || data.items.length === 0) return null;
  return (
    <Card className="mb-6">
      <CardTitle>Your introduction requests</CardTitle>
      <ul className="divide-y divide-slate-100">
        {data.items.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
            <div>
              <p className="font-medium">{r.product_name} <span className="font-normal text-slate-500">· {r.lender_name} · {money(r.requested_amount)}</span> <Badge color={COLOR[r.status]}>{r.status}</Badge></p>
              <p className="text-xs text-slate-500">Shared: {r.shared_fields.join(", ")} · score at the time {r.score_snapshot}</p>
            </div>
            <div className="flex gap-1">{(NEXT[r.status] ?? []).map(([s, l]) => <Button key={s} variant="ghost" onClick={() => mark(r.id, s)}>{l}</Button>)}</div>
          </li>
        ))}
      </ul>
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}
      <p className="mt-3 text-xs text-slate-500">{data.disclaimer} Update the status yourself as the lender responds.</p>
    </Card>
  );
}
