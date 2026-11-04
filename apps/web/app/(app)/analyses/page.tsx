"use client";

import * as React from "react";
import { BarChart3, Play, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  ApiError,
  Card,
  Empty,
  ErrorBox,
  Field,
  formatDate,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";
import { Markdown } from "@/components/intel/Markdown";
import { control } from "@/lib/ui/control";

type Result = {
  markdown: string;
  citations: { document_id: string; title: string | null }[];
  facts_rows: { document_id: string; title: string | null; date: string | null; value: string; currency: string | null }[];
  ai_run_id: number | null;
  uncited?: boolean;
  error?: string;
};
type Analysis = { id: number; name: string; prompt: string; filters: Record<string, unknown>; last_run_at: string | null; last_result: Result | null };
type Template = { id: string; name: string; prompt: string; filters: Record<string, unknown> };

export default function AnalysesPage() {
  const list = useApi<{ items: Analysis[] }>("/api/analyses");
  const templates = useApi<{ items: Template[] }>("/api/analyses/templates");
  const [selected, setSelected] = React.useState<number | null>(null);
  const [running, setRunning] = React.useState<Set<number>>(new Set());
  const [draft, setDraft] = React.useState<{ name: string; prompt: string } | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const startedAt = React.useRef(new Map<number, number>());
  const current = list.data?.items.find((a) => a.id === selected) ?? list.data?.items[0];

  // Poll while a run is in progress (it runs as a background job).
  React.useEffect(() => {
    if (!running.size) return;
    const t = setInterval(async () => {
      const fresh = await api<{ items: Analysis[] }>("/api/analyses").catch(() => null);
      if (!fresh) return;
      list.setData(fresh);
      setRunning((r) => new Set([...r].filter((id) => {
        const a = fresh.items.find((x) => x.id === id);
        const started = startedAt.current.get(id) ?? 0;
        return !(a?.last_run_at && new Date(a.last_run_at).getTime() >= started);
      })));
    }, 3000);
    return () => clearInterval(t);
  }, [running, list]);

  async function create(name: string, prompt: string, filters: Record<string, unknown> = {}) {
    setError(null);
    const a = await api<Analysis>("/api/analyses", { method: "POST", json: { name, prompt, filters } }).catch((e) => (setError(e), null));
    if (a) { list.reload(); setSelected(a.id); setDraft(null); }
  }
  async function run(a: Analysis) {
    setError(null);
    startedAt.current.set(a.id, Date.now() - 1000);
    const ok = await api(`/api/analyses/${a.id}/run`, { method: "POST" }).then(() => true).catch((e) => (setError(e), false));
    if (ok) setRunning((r) => new Set(r).add(a.id));
  }
  async function remove(a: Analysis) {
    const ok = await api(`/api/analyses/${a.id}`, { method: "DELETE" }).then(() => true).catch((e) => (setError(e), false));
    if (ok) { setSelected(null); list.reload(); }
  }

  return (
    <Page>
      <PageHeader title="Analyses" description="Saved questions you can re-run whenever new documents arrive."
        actions={<Button onClick={() => setDraft({ name: "", prompt: "" })}><Plus aria-hidden="true" /> New analysis</Button>} />
      {error && <div className="mb-4"><ErrorBox error={error} /></div>}
      {draft && (
        <Card title="New analysis" className="mb-4">
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create(draft.name, draft.prompt); }}>
            <Field label="Name"><Input required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="Question" help="Written like a chat question. Totals are always computed from your documents.">
              <textarea required className={`${control} h-auto min-h-[5.5rem] py-2`} value={draft.prompt}
                onChange={(e) => setDraft({ ...draft, prompt: e.target.value })} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={() => setDraft(null)}>Cancel</Button>
              <Button type="submit">Save</Button>
            </div>
          </form>
        </Card>
      )}
      {list.loading && !list.data ? <Skeleton rows={4} /> : list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : (
        <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <div className="space-y-4">
            <Card title="Your analyses">
              {list.data?.items.length ? (
                <ul className="space-y-1">
                  {list.data.items.map((a) => (
                    <li key={a.id}>
                      <button onClick={() => setSelected(a.id)} className={`w-full rounded px-3 py-2 text-left hover:bg-surface-2 ${current?.id === a.id ? "bg-surface-2" : ""}`}>
                        <span className="block truncate font-medium">{a.name}</span>
                        <span className="text-xs text-text-muted">{a.last_run_at ? `Last run ${formatDate(a.last_run_at)}` : "Not run yet"}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-text-muted">None yet. Start from a template below.</p>}
            </Card>
            <Card title="Templates">
              <ul className="space-y-2">
                {templates.data?.items.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-2">
                    <span className="text-sm">{t.name}</span>
                    <Button size="sm" variant="secondary" aria-label={`Add ${t.name}`} onClick={() => create(t.name, t.prompt, t.filters)}><Plus aria-hidden="true" /></Button>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          {current ? (
            <Card title={current.name} actions={
              <div className="flex gap-2">
                <Button onClick={() => run(current)} disabled={running.has(current.id)}>
                  <Play aria-hidden="true" /> {running.has(current.id) ? "Running…" : "Run"}
                </Button>
                <Button variant="ghost" aria-label="Delete analysis" onClick={() => remove(current)}><Trash2 aria-hidden="true" /></Button>
              </div>}>
              <p className="mb-4 max-w-[65ch] text-sm text-text-muted">{current.prompt}</p>
              {running.has(current.id) ? <Skeleton rows={4} /> : current.last_result ? (
                current.last_result.error ? (
                  <ErrorBox error={new Error("The analysis could not finish. Check Settings → AI, then run it again.")} onRetry={() => run(current)} />
                ) : (
                  <Markdown text={current.last_result.markdown}
                    titles={Object.fromEntries(current.last_result.citations.map((c) => [c.document_id, c.title ?? "Document"]))} />
                )
              ) : <Empty icon={BarChart3} text="Run this analysis to see the result." />}
            </Card>
          ) : <Empty icon={BarChart3} text="Create an analysis or add a template to get started." />}
        </div>
      )}
    </Page>
  );
}
