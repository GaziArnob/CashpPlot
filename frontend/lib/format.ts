export function money(n: number | null | undefined, currency = "USD") {
  if (currency.toUpperCase() === "RMB") currency = "CNY"; // RMB is the everyday name for the yuan (ISO code CNY)
  if (n === null || n === undefined) return "—";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0, ...(currency === "CNY" ? { currencyDisplay: "narrowSymbol" as const } : {}) }).format(Math.round(n));
  } catch {
    return `${currency} ${Math.round(n).toLocaleString("en-US")}`; // not a recognised currency code
  }
}

export function compact(n: number) {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${Math.round(n / 1_000)}k`;
  return `${Math.round(n)}`;
}

export function shortDate(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function longDate(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}
