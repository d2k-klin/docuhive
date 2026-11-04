"use client";

import Link from "next/link";
import { BookOpen, ShieldCheck } from "lucide-react";
import {
  Badge,
  Card,
  ErrorBox,
  formatDate,
  LocalBadge,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type Provider = { name: string; kind: string; enabled: boolean; local: boolean; experimental: boolean; reachable: boolean; note: string };
type Routing = { tasks: Record<string, { routes: { route: string; local: boolean }[]; apply: { auto: boolean; threshold: number } | null }>; privacy: { local_only: boolean; restricted_tags: string[] }; ai_enabled: boolean };
type Usage = { month: string; providers: { provider: string; runs: number; tokens_in: number; tokens_out: number; cost_usd: number; budget_usd: number | null; pct_used: number | null }[]; privacy: { local_runs: number; cloud_runs: number; restricted_runs: number; skipped_documents: number } };
type Run = { id: number; at: string; task: string; document_id: string | null; provider: string; model: string; local: boolean; status: string; latency_ms: number | null };

const TASK = { triage: "Email triage", classify: "Classify", extract: "Extract facts", embed: "Semantic index", chat: "Ask", analyse: "Analyses" } as Record<string, string>;
const LEARN = [
  ["01", "Strands basics", "strands-basics"], ["02", "Structured output", "structured-output"],
  ["03", "Model providers", "model-providers"], ["04", "The agent harness", "agent-harness"],
  ["05", "Privacy routing", "privacy-routing"], ["06", "Tools and the agent loop", "tools-and-agent-loop"],
  ["07", "Numbers without hallucination", "numbers-without-hallucination"], ["08", "Embeddings and chunking", "embeddings-and-chunking"],
  ["10", "Evals", "evals"], ["11", "The email triage agent", "email-triage-agent"],
];

export default function AISettingsPage() {
  const providers = useApi<Provider[]>("/api/ai/providers");
  const routing = useApi<Routing>("/api/ai/routing");
  const usage = useApi<Usage>("/api/ai/usage");
  const runs = useApi<{ items: Run[] }>("/api/ai/runs?limit=50");
  return (
    <Page>
      <PageHeader title="AI" description="Which models run which task, what it cost this month, and every run. Change routing in your overlay's routing.yaml." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Providers">
          {providers.error ? <ErrorBox error={providers.error} onRetry={providers.reload} /> : !providers.data ? <Skeleton rows={4} /> : (
            <ul className="divide-y divide-border">
              {providers.data.map((p) => (
                <li key={p.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="flex items-center gap-2 font-medium">{p.name} <LocalBadge local={p.local} />
                    {p.experimental && <Badge tone="warn">Experimental</Badge>}</span>
                  {!p.enabled ? <Badge>Off</Badge> : p.note === "not used" ? <Badge>Not used</Badge> :
                    <Badge tone={p.reachable ? "ok" : "error"}>{p.reachable ? "Ready" : p.note}</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Privacy this month" actions={<ShieldCheck aria-hidden="true" className="size-4 text-success" />}>
          {!usage.data ? <Skeleton rows={2} /> : (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-text-muted">Local runs</dt><dd className="tabular text-lg font-semibold">{usage.data.privacy.local_runs}</dd></div>
              <div><dt className="text-text-muted">Cloud runs</dt><dd className="tabular text-lg font-semibold">{usage.data.privacy.cloud_runs}</dd></div>
              <div><dt className="text-text-muted">Restricted documents (all local)</dt><dd className="tabular text-lg font-semibold">{usage.data.privacy.restricted_runs}</dd></div>
              <div><dt className="text-text-muted">Skipped for privacy</dt><dd className="tabular text-lg font-semibold">{usage.data.privacy.skipped_documents}</dd></div>
            </dl>
          )}
          {routing.data?.privacy.local_only && <p className="mt-3"><Badge tone="ok">Local only is on for everything</Badge></p>}
        </Card>
        <Card title="Routing">
          {!routing.data ? <Skeleton rows={6} /> : (
            <table className="w-full text-sm">
              <tbody>
                {Object.entries(routing.data.tasks).map(([task, t]) => (
                  <tr key={task} className="border-b border-border last:border-0">
                    <td className="py-2 pr-3 font-medium">{TASK[task] ?? task}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-1">
                        {t.routes.map((r, i) => (
                          <span key={r.route} className="flex items-center gap-1 text-xs">
                            {i > 0 && <span className="text-text-subtle">then</span>}
                            <code className="font-mono">{r.route}</code> <LocalBadge local={r.local} />
                          </span>
                        ))}
                      </div>
                      {t.apply && <p className="mt-1 text-xs text-text-muted">{t.apply.auto ? `Applied automatically from ${Math.round(t.apply.threshold * 100)}% confidence` : "Every suggestion goes to Review"}</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title={`Usage ${usage.data?.month ?? ""}`}>
          {!usage.data ? <Skeleton rows={3} /> : !usage.data.providers.length ? <p className="text-sm text-text-muted">No AI runs this month yet.</p> : (
            <ul className="space-y-3">
              {usage.data.providers.map((p) => (
                <li key={p.provider}>
                  <div className="flex justify-between text-sm"><span className="font-medium">{p.provider}</span>
                    <span className="tabular text-text-muted">{p.runs} runs · ${p.cost_usd.toFixed(2)}{p.budget_usd ? ` of $${p.budget_usd}` : ""}</span></div>
                  {p.budget_usd !== null && (
                    <div className="mt-1 h-1.5 overflow-hidden rounded bg-surface-2" role="meter" aria-label={`${p.provider} budget used`}
                      aria-valuenow={p.pct_used ?? 0} aria-valuemin={0} aria-valuemax={100}>
                      <div className={(p.pct_used ?? 0) >= 80 ? "h-full bg-warning" : "h-full bg-primary"} style={{ width: `${Math.min(100, p.pct_used ?? 0)}%` }} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Card title="Recent runs" className="mt-4">
        {runs.error ? <p className="text-sm text-text-muted">Only admins can see all runs. Each document shows its own runs.</p> : !runs.data ? <Skeleton rows={5} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border text-left text-xs text-text-muted">
                <th className="px-3 py-2 font-medium">When</th><th className="px-3 py-2 font-medium">Task</th>
                <th className="px-3 py-2 font-medium">Model</th><th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Time</th></tr></thead>
              <tbody>
                {runs.data.items.map((r) => (
                  <tr key={r.id} className="border-b border-border hover:bg-surface-2">
                    <td className="px-3 py-2"><Link className="hover:underline" href={`/settings/ai/runs/${r.id}`}>{formatDate(r.at)}</Link></td>
                    <td className="px-3 py-2">{TASK[r.task] ?? r.task}{r.document_id && <> · <Link className="text-text-muted hover:underline" href={`/documents/${r.document_id}`}>document</Link></>}</td>
                    <td className="px-3 py-2"><span className="flex items-center gap-2"><code className="font-mono text-xs">{r.provider}/{r.model}</code><LocalBadge local={r.local} /></span></td>
                    <td className="px-3 py-2"><Badge tone={r.status === "ok" ? "ok" : r.status === "skipped" ? "muted" : "error"}>{r.status}</Badge></td>
                    <td className="tabular px-3 py-2 text-right">{r.latency_ms !== null ? `${(r.latency_ms / 1000).toFixed(1)} s` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Learn how this works" className="mt-4" actions={<BookOpen aria-hidden="true" className="size-4 text-text-muted" />}>
        <ul className="grid gap-1 sm:grid-cols-2">
          {LEARN.map(([n, label, slug]) => (
            <li key={n}><a className="text-sm hover:underline" target="_blank" rel="noreferrer"
              href={`https://github.com/d2k-klin/docuhive/blob/main/docs/learn/${n}-${slug}.md`}>{n} · {label}</a></li>
          ))}
        </ul>
      </Card>
    </Page>
  );
}
