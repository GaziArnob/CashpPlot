"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui";

/** A button that needs a second, explicit click before it does anything that matters. */
export default function ConfirmAction({ label, prompt, confirmLabel = "Yes, confirm", onConfirm, disabled, variant = "secondary" }: {
  label: ReactNode; prompt: string; confirmLabel?: string; onConfirm: () => Promise<void> | void; disabled?: boolean;
  variant?: "primary" | "secondary" | "ghost";
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!open) {
    return <Button variant={variant} disabled={disabled} onClick={() => setOpen(true)}>{label}</Button>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
      <span className="text-xs text-amber-900">{prompt}</span>
      <Button disabled={busy} onClick={async () => {
        setBusy(true);
        try { await onConfirm(); setOpen(false); } finally { setBusy(false); }
      }}>{busy ? "Working…" : confirmLabel}</Button>
      <Button variant="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>
    </div>
  );
}
