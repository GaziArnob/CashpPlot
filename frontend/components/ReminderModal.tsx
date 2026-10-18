"use client";

import { useState } from "react";
import { CheckCircle2, Send, X } from "lucide-react";
import { Button, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import type { Reminder } from "@/lib/types";

export type ReminderDraft = { reminder: Reminder; customer: string };

export default function ReminderModal({ draft, onClose }: { draft: ReminderDraft; onClose: () => void }) {
  const [text, setText] = useState(draft.reminder.message);
  const [channel, setChannel] = useState("sms");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    try {
      await api(`/reminders/${draft.reminder.id}/send`, { method: "POST", body: JSON.stringify({ message: text, channel }) });
      setSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="font-semibold">Reminder to {draft.customer}</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              {draft.reminder.tone} tone · {draft.reminder.generated_by.startsWith("template") ? "template" : `AI (${draft.reminder.generated_by.split(":")[0]})`}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X className="size-5" /></button>
        </div>
        {sent ? (
          <div className="flex flex-col items-center py-6 text-center">
            <CheckCircle2 className="size-10 text-emerald-600" />
            <p className="mt-3 font-medium">Reminder marked as sent by {channel.toUpperCase()}</p>
            <p className="mt-1 text-xs text-slate-500">Demo mode: no real message was delivered.</p>
            <Button className="mt-5" onClick={onClose}>Done</Button>
          </div>
        ) : (
          <>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6}
              className="w-full rounded-lg border border-slate-300 p-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" />
            {error && <div className="mt-3"><ErrorBox message={error} /></div>}
            <div className="mt-4 flex items-center justify-between gap-3">
              <select value={channel} onChange={(e) => setChannel(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
                <option value="sms">SMS</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="email">Email</option>
              </select>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={onClose}>Cancel</Button>
                <Button onClick={send} disabled={busy}><Send className="size-4" />{busy ? "Sending…" : "Send"}</Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
