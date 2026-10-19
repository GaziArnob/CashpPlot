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
