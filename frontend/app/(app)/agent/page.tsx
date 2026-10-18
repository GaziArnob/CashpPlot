"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Bot, Send, ShieldCheck, User } from "lucide-react";
import { Badge, ErrorBox, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { AgentReply } from "@/lib/types";

type Msg = { role: "user" | "assistant"; content: string; meta?: Omit<AgentReply, "answer"> };

const TOOL_LABEL: Record<string, string> = {
  get_cash_forecast: "cash forecast", get_overdue_customers: "receivables", get_credit_score: "credit score",
  get_loan_recommendation: "loan engine", run_what_if: "what-if", get_spending_insights: "spending",
  draft_reminder: "reminder draft", forecast: "cash forecast", overdue: "receivables", credit: "credit score",
  loan: "loan engine", insights: "spending", reminder: "reminder draft",
};

// Minimal formatting: **bold** and line breaks. Everything else is plain text (no HTML injection).
function renderText(text: string): ReactNode {
  return text.split("\n").map((line, i) => (
    <span key={i}>
      {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
        part.startsWith("**") && part.endsWith("**") ? <strong key={j}>{part.slice(2, -2)}</strong> : part)}
      {i < text.split("\n").length - 1 && <br />}
    </span>
  ));
}

export default function AgentPage() {
  const history = useApi<{ role: "user" | "assistant"; content: string }[]>("/agent/history");
  const suggestions = useApi<{ questions: string[]; llm_configured: boolean }>("/agent/suggestions");
  const [newMessages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const messages: Msg[] = [...(history.data ?? []).slice(-20), ...newMessages];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setBusy(true);
    try {
      const reply = await api<AgentReply>("/agent/chat", { method: "POST", body: JSON.stringify({ message: q }) });
      const { answer, ...meta } = reply;
      setMessages((m) => [...m, { role: "assistant", content: answer, meta }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The assistant could not answer");
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    ask(input);
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col md:h-[calc(100vh-4rem)]">
      <PageHeader title="AI Financial Agent" subtitle="Ask about your cash, customers, credit or loans. Every number comes from your own data."
        right={suggestions.data && (
          <Badge color={suggestions.data.llm_configured ? "green" : "slate"}>
            {suggestions.data.llm_configured ? "Free AI connected" : "Template mode"}
          </Badge>
        )} />

      <div className="flex-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 md:p-6">
        {messages.length === 0 && !busy && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"><Bot className="size-6" /></div>
            <p className="mt-3 font-medium">How can I help with your business today?</p>
            <div className="mt-5 flex max-w-xl flex-wrap justify-center gap-2">
              {suggestions.data?.questions.map((q) => (
                <button key={q} onClick={() => ask(q)}
                  className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:border-emerald-300 hover:bg-emerald-50">
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-5">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
              <div className={`flex size-8 shrink-0 items-center justify-center rounded-full ${m.role === "user" ? "bg-slate-200 text-slate-600" : "bg-emerald-600 text-white"}`}>
                {m.role === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
              </div>
              <div className={`max-w-[80%] ${m.role === "user" ? "text-right" : ""}`}>
                <div className={`inline-block rounded-2xl px-4 py-2.5 text-left text-sm leading-relaxed ${
                  m.role === "user" ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-800"}`}>
                  {renderText(m.content)}
                </div>
                {m.meta && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                    {m.meta.grounded && m.meta.tools_used.length > 0 && (
                      <span className="flex items-center gap-1 text-emerald-700"><ShieldCheck className="size-3.5" />Checked against</span>
                    )}
                    {[...new Set(m.meta.tools_used)].map((t) => <Badge key={t}>{TOOL_LABEL[t] ?? t}</Badge>)}
                    <span className="text-slate-400">· {m.meta.provider}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex gap-3">
              <div className="flex size-8 items-center justify-center rounded-full bg-emerald-600 text-white"><Bot className="size-4" /></div>
              <div className="rounded-2xl bg-slate-100 px-4 py-3">
                <span className="flex gap-1">
                  {[0, 150, 300].map((d) => <span key={d} className="size-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${d}ms` }} />)}
                </span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      {messages.length > 0 && suggestions.data && (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {suggestions.data.questions.map((q) => (
            <button key={q} onClick={() => ask(q)} disabled={busy}
              className="whitespace-nowrap rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 hover:border-emerald-300">
              {q}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={submit} className="mt-3 flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything about your business finances…"
          maxLength={1000}
          className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" />
        <button type="submit" disabled={busy || !input.trim()}
          className="flex items-center justify-center rounded-xl bg-emerald-600 px-4 text-white hover:bg-emerald-700 disabled:bg-emerald-300" aria-label="Send">
          <Send className="size-4" />
        </button>
      </form>
    </div>
  );
}
