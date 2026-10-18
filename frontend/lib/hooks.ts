"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    api<T>(path)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Something went wrong");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  const reload = useCallback(() => {
    setLoading(true);
    setNonce((n) => n + 1);
  }, []);

  return { data, error, loading, reload, setData };
}

export type Business = {
  id: number; name: string; type: string; started_at: string; opening_balance: number; cash_threshold: number;
  currency: string; reminder_tone: "auto" | "friendly" | "firm" | "final"; ai_mode: "cloud" | "local" | "off";
};

let businessCache: Promise<Business> | null = null;

/** The signed-in owner's business (name, currency, settings), fetched once and shared across pages. */
export function useBusiness() {
  const [business, setBusiness] = useState<Business | null>(null);
  useEffect(() => {
    businessCache ??= api<Business>("/settings");
    businessCache.then(setBusiness).catch(() => { businessCache = null; });
  }, []);
  return business;
}

export function forgetBusiness() {
  businessCache = null;
}

export type Me = { id: number; name: string; email: string; role: "owner" | "staff"; totp_enabled: boolean };

/** The signed-in user (role decides which pages show). null until loaded. */
export function useMe() {
  const { data } = useApi<Me>("/auth/me");
  return data;
}
