"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, Lock, MessageSquarePlus, Send, Square, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  api,
  ApiError,
  ErrorBox,
  formatMoney,
  LocalBadge,
  Page,
  Skeleton,
  useApi,
} from "@/components/intel/common";
import { Markdown } from "@/components/intel/Markdown";
import { control, controlSm } from "@/lib/ui/control";
import { cn } from "@/lib/utils";

type Session = { id: number; title: string | null; filters: { categories?: string[] }; local_only: boolean; route: string | null };
type FactsResult = {
  rows: { document_id: string; title: string | null; date: string | null; value: string; currency: string | null }[];
  aggregates: { group: string | null; currency: string | null; value: string | number | null; count: number }[];
};
type ToolCall = { name: string; summary: string; result?: FactsResult };
type Message = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  citations: string[];
  tool_calls: ToolCall[];
  flags: { uncited?: boolean; truncated?: boolean; local?: boolean };
  ai_run_id?: number | null;
  titles?: Record<string, string>;
  error?: { code: string; message: string };
};
type Routes = { items: { route: string; local: boolean; default: boolean }[]; local_only_forced: boolean; local_available: boolean };

const SUGGESTIONS = [
  "How much did I spend on electricity in 2025?",
  "Which contracts can I cancel in the next 3 months?",
  "Show my insurance policies and their premiums",
];
const TOOL_LABEL: Record<string, string> = {
  search_documents: "Searched documents",
  read_document: "Read a document",
  query_facts: "Queried facts",
  list_vocabulary: "Looked up categories",
};
const ERROR_COPY: Record<string, string> = {
  budget_exceeded: "This month's budget for the cloud model is used up. Switch on “Local only” to keep going.",
  no_allowed_route: "No model is allowed to read these documents. Configure a local model in Settings → AI.",
  ai_disabled: "AI is switched off on this server.",
  provider_error: "The model did not answer. Try again, or pick another model.",
};

function FactsTable({ result }: { result: FactsResult }) {
  const totals = result.aggregates.filter((a) => a.group === null && a.value !== null);
  return (
    <div className="mt-3 overflow-x-auto rounded border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-surface-2 text-left text-xs text-text-muted">
            <th className="px-3 py-2 font-medium">Document</th>
            <th className="px-3 py-2 font-medium">Date</th>
            <th className="px-3 py-2 text-right font-medium">Value</th>
          </tr>
        </thead>
        <tbody>
          {result.rows.slice(0, 50).map((r) => (
            <tr key={r.document_id} className="border-b border-border">
              <td className="max-w-64 truncate px-3 py-2">
                <Link className="hover:underline" href={`/documents/${r.document_id}`}>{r.title ?? "Document"}</Link>
              </td>
              <td className="tabular px-3 py-2">{r.date ?? "–"}</td>
              <td className="tabular px-3 py-2 text-right">{formatMoney(r.value, r.currency)}</td>
            </tr>
          ))}
        </tbody>
        {totals.length > 0 && (
          <tfoot>
            {totals.map((t) => (
              <tr key={t.currency ?? "n"} className="font-medium">
                <td className="px-3 py-2" colSpan={2}>Total ({t.count})</td>
                <td className="tabular px-3 py-2 text-right">{formatMoney(String(t.value), t.currency)}</td>
              </tr>
            ))}
          </tfoot>
        )}
      </table>
    </div>
  );
}

function AssistantMessage({ m }: { m: Message }) {
  const facts = m.tool_calls.find((t) => t.name === "query_facts" && t.result?.rows?.length)?.result;
  return (
    <div className="space-y-2">
      {m.tool_calls.length > 0 && (
        <details className="text-xs text-text-muted">
          <summary className="flex cursor-pointer items-center gap-1">
            <Wrench aria-hidden="true" className="size-3" />
            What I did: {[...new Set(m.tool_calls.map((t) => TOOL_LABEL[t.name] ?? t.name))].join(" · ")}
          </summary>
          <ul className="mt-1 list-disc pl-5">
            {m.tool_calls.map((t, i) => (
              <li key={i}>{TOOL_LABEL[t.name] ?? t.name}: {t.summary}</li>
            ))}
          </ul>
          {m.ai_run_id && (
            <Link className="mt-1 inline-block hover:underline" href={`/settings/ai/runs/${m.ai_run_id}`}>Under the hood</Link>
          )}
        </details>
      )}
      {m.content ? <Markdown text={m.content} titles={m.titles} /> : !m.error && <Skeleton rows={1} />}
      {facts && <FactsTable result={facts} />}
      {m.flags.uncited && (
        <p className="flex items-center gap-1 text-xs text-warning">
          <AlertTriangle aria-hidden="true" className="size-3" /> This answer cites no documents. Check it before relying on it.
        </p>
      )}
      {m.flags.truncated && <p className="text-xs text-text-muted">Stopped before the answer was finished.</p>}
      {m.error && (
        <p role="alert" className="flex items-center gap-1 text-sm text-danger">
          <AlertTriangle aria-hidden="true" className="size-4" /> {ERROR_COPY[m.error.code] ?? m.error.message}
        </p>
      )}
    </div>
  );
}

async function* readSse(res: Response): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      if (block.startsWith(":")) continue; // heartbeat
      const event = block.match(/^event: (.*)$/m)?.[1] ?? "message";
      const data = block.match(/^data: (.*)$/m)?.[1];
      if (data) yield { event, data: JSON.parse(data) };
    }
  }
}

export default function AskPage() {
  const sessions = useApi<{ items: Session[] }>("/api/chat/sessions");
  const routes = useApi<Routes>("/api/chat/routes");
  const tax = useApi<{ categories: { id: string; label: string }[] }>("/api/taxonomy");
  const [active, setActive] = React.useState<Session | null>(null);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<ApiError | null>(null);
  const abort = React.useRef<AbortController | null>(null);
  const bottom = React.useRef<HTMLDivElement>(null);
  const forced = routes.data?.local_only_forced ?? false;

  // Braces matter: newer browsers return a Promise from scrollIntoView, and React treats an
  // effect's return value as its cleanup function.
  React.useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  async function open(s: Session) {
    setActive(s);
    setError(null);
    const res = await api<{ items: Message[] }>(`/api/chat/sessions/${s.id}/messages`).catch((e) => (setError(e), null));
    setMessages(res?.items ?? []);
  }

  async function patch(update: Partial<Session>) {
    if (!active) return setActive((a) => a && { ...a, ...update });
    const s = await api<Session>(`/api/chat/sessions/${active.id}`, { method: "PATCH", json: update }).catch((e) => (setError(e), null));
    if (s) setActive(s);
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setError(null);
    let session = active;
    if (!session) {
      session = await api<Session>("/api/chat/sessions", { method: "POST", json: { local_only: forced } }).catch((e) => (setError(e), null));
      if (!session) return;
      setActive(session);
    }
    setInput("");
    setBusy(true);
    const reply: Message = { role: "assistant", content: "", citations: [], tool_calls: [], flags: {}, titles: {} };
    setMessages((m) => [...m, { role: "user", content: text, citations: [], tool_calls: [], flags: {} }, reply]);
    const update = (fn: (m: Message) => Message) =>
      setMessages((all) => [...all.slice(0, -1), fn(all[all.length - 1])]);
    abort.current = new AbortController();
    try {
      // Only the new message goes to the server; it builds the history itself.
      const res = await fetch(`/api/chat/sessions/${session.id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-DocuHive-CSRF": "1" },
        body: JSON.stringify({ content: text }),
        signal: abort.current.signal,
      });
      if (!res.ok) throw new ApiError(`http_${res.status}`, "The chat could not start. Try again.", res.status);
      for await (const { event, data } of readSse(res)) {
        if (event === "token") update((m) => ({ ...m, content: m.content + String(data.text) }));
        else if (event === "tool_result")
          update((m) => ({ ...m, tool_calls: [...m.tool_calls, data as unknown as ToolCall] }));
        else if (event === "citation")
          update((m) => ({ ...m, titles: { ...m.titles, [String(data.document_id)]: String(data.title ?? "Document") } }));
        else if (event === "done")
          update((m) => ({ ...m, id: Number(data.message_id), ai_run_id: Number(data.ai_run_id), flags: { uncited: Boolean(data.uncited), local: Boolean(data.local) } }));
        else if (event === "error")
          update((m) => ({ ...m, error: { code: String(data.code), message: String(data.message) } }));
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") update((m) => ({ ...m, flags: { ...m.flags, truncated: true } }));
      else update((m) => ({ ...m, error: { code: "provider_error", message: (e as Error).message } }));
    } finally {
      setBusy(false);
      sessions.reload();
    }
  }

  const localOnly = forced || Boolean(active?.local_only);
  return (
    <Page>
      <div className="grid gap-4 md:grid-cols-[14rem_minmax(0,1fr)]">
        <aside aria-label="Chats" className="space-y-2">
          <Button className="w-full" onClick={() => { setActive(null); setMessages([]); }}>
            <MessageSquarePlus aria-hidden="true" /> New chat
          </Button>
          {sessions.loading && !sessions.data ? <Skeleton rows={4} /> : (
            <ul className="space-y-1">
              {sessions.data?.items.map((s) => (
                <li key={s.id}>
                  <button onClick={() => open(s)}
                    className={cn("flex h-control w-full items-center rounded px-3 text-left text-sm hover:bg-surface-2",
                      active?.id === s.id && "bg-surface-2 font-medium")}>
                    <span className="truncate">{s.title || "New chat"}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <section className="flex min-h-[70vh] min-w-0 flex-col">
          <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Chat scope">
            <h1 className="mr-auto text-xl font-semibold">Ask</h1>
            <select aria-label="Category" className={cn(controlSm, "w-48")}
              value={active?.filters?.categories?.[0] ?? ""}
              onChange={(e) => patch({ filters: e.target.value ? { categories: [e.target.value] } : {} })}>
              <option value="">All categories</option>
              {tax.data?.categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <select aria-label="Model" className={cn(controlSm, "w-56")} value={active?.route ?? ""}
              onChange={(e) => patch({ route: e.target.value || null })} disabled={localOnly}>
              <option value="">Default model</option>
              {routes.data?.items.map((r) => <option key={r.route} value={r.route}>{r.route}{r.local ? " (local)" : ""}</option>)}
            </select>
            <label className="flex h-control-sm items-center gap-2 text-sm">
              <input type="checkbox" className="size-4" checked={localOnly} disabled={forced || !routes.data?.local_available}
                onChange={(e) => patch({ local_only: e.target.checked })} />
              {forced && <Lock aria-hidden="true" className="size-3" />} Local only
            </label>
            <LocalBadge local={localOnly || Boolean(routes.data?.items.find((r) => r.default)?.local)} />
          </div>
          {error && <div className="mb-3"><ErrorBox error={error} /></div>}
          <div className="flex-1 space-y-6 pb-4" aria-live="polite">
            {messages.length === 0 ? (
              <div className="mx-auto max-w-xl space-y-3 pt-8 text-center">
                <p className="text-text-muted">Ask about your documents. Answers cite the documents they come from, and totals are computed from your data.</p>
                <div className="flex flex-col gap-2">
                  {SUGGESTIONS.map((s) => (
                    // A wrapping control, like the tag input: control height on one line, taller when the
                    // question wraps, so the full text is always visible before it is sent.
                    // `!`: cn() only joins classes, so it can't override Button's own classes.
                    <Button key={s} variant="secondary" onClick={() => send(s)} data-wrap
                      className="!h-auto min-h-control !justify-start py-1.5 text-left !whitespace-normal">{s}</Button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => m.role === "user" ? (
                <div key={i} className="ml-auto max-w-[80%] rounded-card bg-surface-2 px-4 py-2">{m.content}</div>
              ) : (
                <div key={i} className="max-w-full"><AssistantMessage m={m} /></div>
              ))
            )}
            <div ref={bottom} />
          </div>
          <form className="sticky bottom-0 flex gap-2 border-t border-border bg-bg py-3"
            onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <textarea aria-label="Your question" rows={1} value={input} placeholder="Ask about your documents…"
              className={cn(control, "h-auto min-h-control resize-none py-2")}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} />
            {busy ? (
              <Button type="button" variant="secondary" aria-label="Stop" onClick={() => abort.current?.abort()}><Square aria-hidden="true" /></Button>
            ) : (
              <Button type="submit" aria-label="Send" disabled={!input.trim()}><Send aria-hidden="true" /></Button>
            )}
          </form>
        </section>
      </div>
    </Page>
  );
}
