"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { BookOpen } from "lucide-react";
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

type Attempt = { id: number; at: string; provider: string; model: string; local: boolean; status: string; latency_ms: number | null; error: string | null };
type Run = Attempt & {
  task: string;
  document_id: string | null;
  restricted: boolean;
  prompt_version: string;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  output: unknown;
  attempts: Attempt[];
  prompt_text: string | null;
  learn: string | null;
  privacy: string;
};

const tone = (status: string) => (status === "ok" ? "ok" : status === "skipped" ? undefined : "error");
const TASK: Record<string, string> = { triage: "Email triage", classify: "Classify", extract: "Extract facts", embed: "Semantic index", chat: "Ask", analyse: "Analyses" };

/** "How was this made?": one AI run with its model, prompt, output, cost and retries. */
export default function AIRunPage() {
  const { id } = useParams<{ id: string }>();
  const run = useApi<Run>(`/api/ai/runs/${encodeURIComponent(id)}`);
  if (run.error) return <Page><ErrorBox error={run.error} onRetry={run.reload} /></Page>;
  if (!run.data) return <Page><Skeleton rows={8} /></Page>;
  const r = run.data;
  const facts: [string, React.ReactNode][] = [
    ["Model", <span key="m" className="flex items-center gap-2">{r.provider} · {r.model} <LocalBadge local={r.local} /></span>],
    ["Prompt", r.prompt_version],
    ["Privacy", r.privacy],
    ["Tokens", r.tokens_in != null ? `${r.tokens_in} in · ${r.tokens_out ?? 0} out` : "—"],
    ["Cost", r.cost_usd != null ? `$${r.cost_usd.toFixed(4)}` : "—"],
    ["Time", r.latency_ms != null ? `${(r.latency_ms / 1000).toFixed(1)} s` : "—"],
  ];
  return (
    <Page>
      <PageHeader
        title="How was this made?"
        description={`${TASK[r.task] ?? r.task} · ${formatDate(r.at)}`}
        actions={r.document_id && <Link className="text-sm text-primary hover:underline" href={`/documents/${r.document_id}`}>Open the document</Link>}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Run" actions={<Badge tone={tone(r.status)}>{r.status}</Badge>}>
          <dl className="space-y-2 text-sm">
            {facts.map(([label, value]) => (
              <div key={label} className="flex flex-wrap justify-between gap-2"><dt className="text-text-muted">{label}</dt><dd className="tabular">{value}</dd></div>
            ))}
          </dl>
          {r.error && <p role="alert" className="mt-3 text-sm text-danger">{r.error}</p>}
          {r.learn && (
            <a className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline" target="_blank" rel="noreferrer"
              href={`https://github.com/d2k-klin/docuhive/blob/main/${r.learn}`}><BookOpen aria-hidden="true" className="size-4" /> Learn how this works</a>
          )}
        </Card>
        <Card title="Attempts">
          {r.attempts.length > 1 ? (
            <ol className="space-y-1 text-sm">
              {r.attempts.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-2">
                  {a.id === r.id ? <span className="font-medium">This run</span> : <Link className="hover:underline" href={`/settings/ai/runs/${a.id}`}>{formatDate(a.at)}</Link>}
                  <span className="text-text-muted">{a.model}</span><Badge tone={tone(a.status)}>{a.status}</Badge>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-text-muted">The first attempt; nothing was retried.</p>}
        </Card>
        <Card title="Output">
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(r.output, null, 2) ?? "—"}</pre>
        </Card>
        <Card title="Prompt">
          {r.prompt_text ? <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{r.prompt_text}</pre>
            : <p className="text-sm text-text-muted">The prompt file for {r.prompt_version} is not on this server.</p>}
        </Card>
      </div>
    </Page>
  );
}
