"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { Check, Copy, ShieldCheck } from "lucide-react";
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { INPUT } from "@/components/Modal";
import { api, downloadFile, logout } from "@/lib/api";
import { forgetBusiness, useApi, useMe, type Business } from "@/lib/hooks";

type Plan = {
  plan: string; effective_plan: "free" | "pro"; trial: boolean; trial_ended: boolean; days_left: number | null;
  free_forecast_days: number; note: string | null; billing_mode: string; can_checkout: boolean; has_subscription: boolean;
  features: Record<string, { label: string; included: boolean }>;
};
type Member = { id: number; name: string; email: string; active: boolean; two_factor: boolean };
type Team = { max_staff: number; members: Member[]; can_do: string[]; cannot_do: string[] };
type Access = { id: number; lender_name: string; scope: string[]; expires_at: string; active: boolean };

const SCOPES = [
  ["credit_score", "Credit score"], ["pnl", "Last month's profit & loss"], ["cash_forecast", "30-day cash forecast"],
] as const;
const AI_MODES = [
  ["cloud", "Cloud AI", "Wording is polished by a hosted model. Names are replaced with codes first; figures never leave the engines."],
  ["local", "Local only", "Only a model running on your own machine is used. Nothing is sent to a hosted AI."],
  ["off", "Off", "No AI model. Built-in templates write every message and summary."],
] as const;

function Section({ id, title, children, right }: { id?: string; title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6">
      <Card><CardTitle right={right}>{title}</CardTitle>{children}</Card>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="text-sm font-medium text-slate-700">{label}</span>{children}</label>;
}

function useAction() {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run<T>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> {
    setError(null);
    setNotice(null);
    try {
      const r = await fn();
      if (ok) setNotice(ok);
      return r;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  }
  return { error, notice, run };
}

function Msg({ a }: { a: ReturnType<typeof useAction> }) {
  return <>
    {a.error && <div className="mt-3"><ErrorBox message={a.error} /></div>}
    {a.notice && <p className="mt-3 flex items-center gap-1.5 text-sm text-emerald-700"><Check className="size-4" />{a.notice}</p>}
  </>;
}

function Profile({ b, onSaved }: { b: Business; onSaved: () => void }) {
  const a = useAction();
  const [f, setF] = useState({ name: b.name, type: b.type, currency: b.currency, cash_threshold: String(b.cash_threshold), reminder_tone: b.reminder_tone });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  async function save(e: FormEvent) {
    e.preventDefault();
    await a.run(async () => {
      await api("/settings", { method: "PUT", body: JSON.stringify({ ...f, cash_threshold: Number(f.cash_threshold) || 0, currency: f.currency.toUpperCase() }) });
      forgetBusiness();
      onSaved();
    }, "Saved");
  }
  return (
    <Section title="Business profile">
      <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
        <Field label="Business name"><input required className={INPUT} value={f.name} onChange={set("name")} /></Field>
        <Field label="Business type"><input className={INPUT} value={f.type} onChange={set("type")} /></Field>
        <Field label="Currency (ISO code, e.g. USD, EUR, INR)"><input required maxLength={8} className={INPUT} value={f.currency} onChange={set("currency")} /></Field>
        <Field label="Safety cash threshold"><input type="number" min={0} className={INPUT} value={f.cash_threshold} onChange={set("cash_threshold")} /></Field>
        <Field label="Payment reminder tone">
          <select className={INPUT} value={f.reminder_tone} onChange={set("reminder_tone")}>
            <option value="auto">Automatic (by how late)</option><option value="friendly">Friendly</option>
            <option value="firm">Firm</option><option value="final">Final notice</option>
          </select>
        </Field>
        <div className="flex items-end"><Button type="submit">Save changes</Button></div>
      </form>
      <Msg a={a} />
    </Section>
  );
}

function AiPrivacy({ b, onSaved }: { b: Business; onSaved: () => void }) {
  const a = useAction();
  return (
    <Section title="AI privacy">
      <div className="space-y-2">
        {AI_MODES.map(([value, label, text]) => (
          <button key={value} type="button" onClick={() => a.run(async () => {
            await api("/settings", { method: "PUT", body: JSON.stringify({ ai_mode: value }) });
            forgetBusiness();
            onSaved();
          }, `AI mode set to ${label}`)}
            className={`block w-full rounded-lg border p-3 text-left text-sm ${b.ai_mode === value ? "border-emerald-500 bg-emerald-50" : "border-slate-200 hover:bg-slate-50"}`}>
            <span className="font-medium">{label}</span> {b.ai_mode === value && <Badge color="green">selected</Badge>}
            <span className="mt-0.5 block text-slate-500">{text}</span>
          </button>
        ))}
      </div>
      <Msg a={a} />
    </Section>
  );
}

function PlanCard({ plan, reload }: { plan: Plan; reload: () => void }) {
  const a = useAction();
  const change = (p: "free" | "pro") => a.run(async () => {
    await api("/billing/plan", { method: "POST", body: JSON.stringify({ plan: p, confirm: true }) });
    reload();
  }, p === "pro" ? "You are on Pro" : "You are on Free");
  const pro = plan.effective_plan === "pro";
  const goTo = (path: string) => a.run(async () => {
    const r = await api<{ url: string }>(path, { method: "POST" });
    window.location.href = r.url;
  });
  const stripe = plan.billing_mode === "stripe";
  return (
    <Section id="plan" title="Plan & billing" right={<Badge color={pro ? "green" : "slate"}>{pro ? "Pro" : "Free"}</Badge>}>
      {plan.trial && <p className="mb-3 text-sm text-slate-600">Free Pro trial: <b>{plan.days_left} day{plan.days_left === 1 ? "" : "s"} left</b>. After that you move to Free unless you choose Pro.</p>}
      {plan.trial_ended && <p className="mb-3 text-sm text-amber-700">Your Pro trial has ended. Choose Pro to keep the full feature set.</p>}
      <ul className="grid gap-1.5 text-sm sm:grid-cols-2">
        <li className="flex gap-2"><Check className="size-4 text-emerald-600" /> Transactions, customers, invoices, dashboard, {plan.free_forecast_days}-day forecast (Free)</li>
        {Object.values(plan.features).map((f) => (
          <li key={f.label} className={`flex gap-2 ${f.included ? "" : "text-slate-400"}`}>
            <Check className={`size-4 ${f.included ? "text-emerald-600" : "text-slate-300"}`} /> {f.label} <span className="text-xs">(Pro)</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex gap-2">
        {stripe ? (
          <>
            {!(pro && plan.has_subscription) && <Button disabled={!plan.can_checkout} onClick={() => goTo("/billing/checkout")}>Upgrade to Pro</Button>}
            {plan.has_subscription && <Button variant="secondary" onClick={() => goTo("/billing/portal")}>Manage billing</Button>}
          </>
        ) : pro ? <Button variant="secondary" onClick={() => change("free")}>Switch to Free</Button> : <Button onClick={() => change("pro")}>Choose Pro</Button>}
      </div>
      {plan.note && <p className="mt-3 text-xs text-slate-500">{plan.note}</p>}
      <Msg a={a} />
    </Section>
  );
}

function TeamCard() {
  const team = useApi<Team>("/team");
  const a = useAction();
  const [f, setF] = useState({ name: "", email: "", password: "" });
  if (team.loading && !team.data) return <Section title="Team"><Loading /></Section>;
  if (!team.data) return <Section title="Team"><ErrorBox message={team.error ?? "No data"} onRetry={team.reload} /></Section>;
  const t = team.data;
  const act = (path: string, init: RequestInit, ok: string) => a.run(async () => { await api(path, init); team.reload(); }, ok);
  async function add(e: FormEvent) {
    e.preventDefault();
    await a.run(async () => {
      await api("/team", { method: "POST", body: JSON.stringify(f) });
      setF({ name: "", email: "", password: "" });
      team.reload();
    }, "Staff login created. Give them the password in person.");
  }
  return (
    <Section title="Team" right={<span className="text-xs text-slate-500">{t.members.length} of {t.max_staff}</span>}>
      <div className="mb-4 grid gap-4 text-sm sm:grid-cols-2">
        <div><p className="mb-1 font-medium text-emerald-700">Staff can</p><ul className="list-disc pl-5 text-slate-600">{t.can_do.map((x) => <li key={x}>{x}</li>)}</ul></div>
        <div><p className="mb-1 font-medium text-rose-700">Staff cannot</p><ul className="list-disc pl-5 text-slate-600">{t.cannot_do.map((x) => <li key={x}>{x}</li>)}</ul></div>
      </div>
      {t.members.length > 0 && (
        <ul className="mb-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
          {t.members.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
              <div><span className="font-medium">{m.name}</span> <span className="text-slate-500">{m.email}</span> {!m.active && <Badge color="red">removed</Badge>}</div>
              <div className="flex gap-1">
                {m.active ? <>
                  <Button variant="ghost" onClick={() => {
                    const password = window.prompt(`New password for ${m.name} (min 8 characters)`);
                    if (password) act(`/team/${m.id}/password`, { method: "POST", body: JSON.stringify({ password }) }, "Password changed");
                  }}>Reset password</Button>
                  <Button variant="ghost" onClick={() => window.confirm(`Remove ${m.name}? They are signed out at once.`) && act(`/team/${m.id}`, { method: "DELETE" }, "Removed")}>Remove</Button>
                </> : <Button variant="ghost" onClick={() => act(`/team/${m.id}/reactivate`, { method: "POST" }, "Restored")}>Restore</Button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="grid gap-3 sm:grid-cols-4">
        <Field label="Name"><input required className={INPUT} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email"><input required type="email" className={INPUT} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="First password"><input required minLength={8} type="password" className={INPUT} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <div className="flex items-end"><Button type="submit">Add staff</Button></div>
      </form>
      <Msg a={a} />
    </Section>
  );
}

function LenderAccessCard() {
  const list = useApi<Access[]>("/lender-access");
  const a = useAction();
  const [lender, setLender] = useState("");
  const [scope, setScope] = useState<string[]>(["credit_score", "pnl"]);
  const [days, setDays] = useState("30");
  const [consent, setConsent] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const locked = list.error?.startsWith("Upgrade to Pro");
  async function grant(e: FormEvent) {
    e.preventDefault();
    await a.run(async () => {
      const r = await api<{ token: string }>("/lender-access", { method: "POST", body: JSON.stringify({ lender_name: lender, scope, days_valid: Number(days) }) });
      setToken(r.token);
      setLender("");
      setConsent(false);
      list.reload();
    });
  }
  return (
    <Section title="Lender access">
      <p className="mb-3 text-sm text-slate-500">Give one lender read-only access to the items you choose, for a limited time. You can revoke it at any time.</p>
      {locked ? <ErrorBox message={list.error!} /> : <>
        {token && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
            <p className="font-medium text-amber-900">Copy this token now. It will not be shown again.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded bg-white px-2 py-1 text-xs">{token}</code>
              <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(token); setCopied(true); }}><Copy className="size-4" />{copied ? "Copied" : "Copy"}</Button>
            </div>
            <p className="mt-2 text-xs text-amber-800">The lender opens <b>/lender</b> and pastes it there.</p>
          </div>
        )}
        {(list.data ?? []).length > 0 && (
          <ul className="mb-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {list.data!.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <div><span className="font-medium">{x.lender_name}</span> <span className="text-slate-500">{x.scope.join(", ")} · until {x.expires_at.slice(0, 10)}</span> {x.active ? <Badge color="green">active</Badge> : <Badge>ended</Badge>}</div>
                {x.active && <Button variant="ghost" onClick={() => a.run(async () => { await api(`/lender-access/${x.id}`, { method: "DELETE" }); list.reload(); }, "Access revoked")}>Revoke</Button>}
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={grant} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Lender name"><input required className={INPUT} value={lender} onChange={(e) => setLender(e.target.value)} /></Field>
            <Field label="Valid for (days)"><input type="number" min={1} max={365} className={INPUT} value={days} onChange={(e) => setDays(e.target.value)} /></Field>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            {SCOPES.map(([v, l]) => (
              <label key={v} className="flex items-center gap-2">
                <input type="checkbox" checked={scope.includes(v)} onChange={(e) => setScope(e.target.checked ? [...scope, v] : scope.filter((s) => s !== v))} /> {l}
              </label>
            ))}
          </div>
          <label className="flex items-start gap-2 text-sm text-slate-600">
            <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            I agree to share the selected information with this lender.
          </label>
          <Button type="submit" disabled={!consent || scope.length === 0}>Grant access</Button>
        </form>
      </>}
      <Msg a={a} />
    </Section>
  );
}

function TwoFactorCard({ enabled, reload }: { enabled: boolean; reload: () => void }) {
  const a = useAction();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  return (
    <Section title="Two-factor sign-in" right={enabled ? <Badge color="green">on</Badge> : <Badge>off</Badge>}>
      <p className="mb-3 text-sm text-slate-500">Ask for a 6-digit code from an authenticator app (Google Authenticator, Authy, 1Password and similar) every time you sign in.</p>
      {!enabled && !setup && <Button onClick={async () => setSetup(await a.run(() => api<{ secret: string; otpauth_uri: string }>("/auth/2fa/setup", { method: "POST" })) ?? null)}><ShieldCheck className="size-4" />Set up</Button>}
      {!enabled && setup && (
        <div className="space-y-3 text-sm">
          <p>In your authenticator app choose “Enter a setup key” and type this key:</p>
          <code className="block break-all rounded bg-slate-100 px-3 py-2 text-sm font-semibold tracking-wider">{setup.secret}</code>
          <p className="text-xs text-slate-500">Or open this link on the phone with the app: <span className="break-all">{setup.otpauth_uri}</span></p>
          <div className="flex items-end gap-2">
            <Field label="Code from the app"><input inputMode="numeric" maxLength={6} className={INPUT} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
            <Button onClick={async () => { if (await a.run(() => api("/auth/2fa/enable", { method: "POST", body: JSON.stringify({ code }) }), "Two-factor sign-in is on")) { setSetup(null); setCode(""); reload(); } }}>Turn on</Button>
          </div>
        </div>
      )}
      {enabled && (
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <Field label="Password"><input type="password" className={INPUT} value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <Field label="Current code"><input inputMode="numeric" maxLength={6} className={INPUT} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
          <Button variant="secondary" onClick={async () => { if (await a.run(() => api("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ password, code }) }), "Two-factor sign-in is off")) { setPassword(""); setCode(""); reload(); } }}>Turn off</Button>
        </div>
      )}
      <Msg a={a} />
    </Section>
  );
}

function DataCard() {
  const router = useRouter();
  const a = useAction();
  const [confirm, setConfirm] = useState("");
  return (
    <Section title="Your data">
      <p className="mb-3 text-sm text-slate-500">Download everything we hold about your business, or delete the account and all of its data permanently.</p>
      <Button variant="secondary" onClick={() => a.run(() => downloadFile("/settings/export", "cashpilot-export.json"))}>Download my data (JSON)</Button>
      <div className="mt-5 border-t border-slate-100 pt-4">
        <p className="text-sm font-medium text-rose-700">Delete account</p>
        <p className="mb-2 text-xs text-slate-500">This removes the business, all records and every staff login. It cannot be undone. Type DELETE to confirm.</p>
        <div className="flex gap-2">
          <input className={`${INPUT} max-w-48`} value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="DELETE" />
          <Button variant="secondary" disabled={confirm !== "DELETE"} onClick={() => a.run(async () => {
            await api("/settings/account", { method: "DELETE" });
            forgetBusiness();
            await logout().catch(() => {});
            router.replace("/signup");
          })}>Delete everything</Button>
        </div>
      </div>
      <Msg a={a} />
    </Section>
  );
}

type Prefs = { types: { type: string; label: string; severity: string; muted: boolean }[]; email: boolean; email_available: boolean };

function NotificationsCard() {
  const prefs = useApi<Prefs>("/notifications/preferences");
  const a = useAction();
  const [muted, setMuted] = useState<string[] | null>(null);
  const [email, setEmail] = useState<boolean | null>(null);
  if (!prefs.data) return <Section id="notifications" title="Notifications">{prefs.error ? <ErrorBox message={prefs.error} onRetry={prefs.reload} /> : <Loading />}</Section>;
  const p = prefs.data;
  const mutedNow = muted ?? p.types.filter((t) => t.muted).map((t) => t.type);
  const emailNow = email ?? p.email;
  const toggle = (type: string, on: boolean) => setMuted(on ? mutedNow.filter((m) => m !== type) : [...mutedNow, type]);
  return (
    <Section id="notifications" title="Notifications">
      <p className="mb-3 text-sm text-slate-500">Choose which alerts you get. Each one appears once, and again only if it is still unresolved days later.</p>
      <ul className="space-y-2 text-sm">
        {p.types.map((t) => (
          <li key={t.type}>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={!mutedNow.includes(t.type)} onChange={(e) => toggle(t.type, e.target.checked)} />
              {t.label} {t.severity === "critical" && <Badge color="red">urgent</Badge>}
            </label>
          </li>
        ))}
      </ul>
      <label className={`mt-4 flex items-start gap-2 text-sm ${p.email_available ? "" : "text-slate-400"}`}>
        <input type="checkbox" className="mt-1" disabled={!p.email_available} checked={emailNow} onChange={(e) => setEmail(e.target.checked)} />
        <span>Also email me urgent alerts{!p.email_available && " (email is not set up on this server yet)"}</span>
      </label>
      <div className="mt-4">
        <Button onClick={() => a.run(async () => {
          await api("/notifications/preferences", { method: "PUT", body: JSON.stringify({ muted: mutedNow, email: emailNow && p.email_available }) });
          setMuted(null);
          setEmail(null);
          prefs.reload();
        }, "Saved")}>Save</Button>
      </div>
      <Msg a={a} />
    </Section>
  );
}

export default function SettingsPage() {
  const me = useMe();
  const biz = useApi<Business>("/settings");
  const plan = useApi<Plan>("/billing/plan");
  const [version, setVersion] = useState(0);
  if (biz.loading && !biz.data) return <Loading />;
  if (!biz.data) return <ErrorBox message={biz.error ?? "No data"} onRetry={biz.reload} />;
  return (
    <>
      <PageHeader title="Settings" subtitle="Business, team, plan, privacy and security" />
      <div className="space-y-6">
        <Profile key={`p${version}`} b={biz.data} onSaved={() => { biz.reload(); setVersion((v) => v + 1); }} />
        <AiPrivacy b={biz.data} onSaved={biz.reload} />
        {plan.data ? <PlanCard plan={plan.data} reload={plan.reload} /> : plan.error ? <ErrorBox message={plan.error} /> : <Loading />}
        <TeamCard />
        <LenderAccessCard key={plan.data?.effective_plan} />
        <NotificationsCard />
        {me && <TwoFactorCard enabled={me.totp_enabled} reload={() => window.location.reload()} />}
        <DataCard />
      </div>
    </>
  );
}
