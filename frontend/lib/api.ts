"use client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "cashpilot_token";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the session just won't survive a reload */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function refreshToken(): Promise<boolean> {
  try {
    const r = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "X-Requested-With": "fetch" },
    });
    if (!r.ok) return false;
    setToken((await r.json()).access_token);
    return true;
  } catch {
    return false;
  }
}

export async function api<T = unknown>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let r: Response;
  try {
    r = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_URL}. Is it running?`);
  }
  if (r.status === 401 && retry && path !== "/auth/login") {
    if (await refreshToken()) return api<T>(path, init, false);
    setToken(null);
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const body = await r.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) {
        // FastAPI validation errors: show "field: message" instead of raw JSON
        msg = body.detail
          .map((e: { loc?: string[]; msg?: string }) => `${e.loc?.at(-1) ?? "input"}: ${e.msg ?? "invalid"}`)
          .join("; ");
      } else msg = JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export async function login(email: string, password: string) {
  const r = await api<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(r.access_token);
}

export async function logout() {
  try {
    await api("/auth/logout", { method: "POST" }, false);
  } finally {
    setToken(null);
  }
}
