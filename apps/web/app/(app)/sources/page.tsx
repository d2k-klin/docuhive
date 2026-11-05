"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { History, Mail, Pause, Play, RefreshCw, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  ApiError,
  Badge,
  Card,
  ErrorBox,
  Field,
  formatDate,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";
import { ConnectMailbox, type Connection, type Oauth } from "@/components/intel/ConnectMailbox";
import { controlSm } from "@/lib/ui/control";

type Account = { id: number; provider: "gmail" | "graph" | "imap"; address: string; display_name: string | null; status: string; last_sync_at: string | null };
type Backfill = { id: number; account_id: number; date_from: string; date_to: string; status: string; scanned: number; candidates: number; imported: number; duplicates: number; errors: number; last_error: string | null };
type Msg = { id: number; received_at: string; email_from: string | null; subject: string | null; status: string; reason: string | null; triage_confidence: number | null; attachments: { filename: string; status: string; document_id: string | null }[] };

const PROVIDER = { gmail: "Gmail", graph: "Outlook", imap: "IMAP" };
const STATUS_TONE: Record<string, "ok" | "warn" | "error" | "muted" | "info"> = {
  active: "ok", paused: "muted", needs_reauth: "error", error: "error",
  imported: "ok", partial: "warn", triage_rejected: "muted", prefiltered_out: "muted", new: "info",
  running: "info", done: "ok", cancelled: "muted",
};
const STATUS_TEXT: Record<string, string> = {
  active: "Active", paused: "Paused", needs_reauth: "Reconnect needed", error: "Error",
  imported: "Imported", partial: "Partly imported", triage_rejected: "Not a document",
  prefiltered_out: "Skipped by rules", new: "Waiting", running: "Running", done: "Done", cancelled: "Cancelled",
};
const PRESETS = [
  { label: "Last 30 days", days: 30 },
  { label: "Last year", years: 1 },
  { label: "Last 3 years", years: 3 },
  { label: "Since 2015", since: "2015-01-01" },
];

function daysAgo(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isoDaysAgo(years: number) {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
}


function BackfillCard({ b, onChange, onError }: { b: Backfill; onChange: () => void; onError: (error: ApiError) => void }) {
  const act = (action: string) => api(`/api/sources/backfills/${b.id}/${action}`, { method: "POST" }).then(onChange).catch(onError);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-border p-3">
      <div>
        <div className="flex items-center gap-2 font-medium">
          {formatDate(b.date_from)} – {formatDate(b.date_to)}
          <Badge tone={STATUS_TONE[b.status]}>{STATUS_TEXT[b.status] ?? b.status}</Badge>
        </div>
        <p className="tabular text-xs text-text-muted">
          {b.scanned} scanned · {b.imported} imported · {b.duplicates} already archived · {b.errors} failed
          {b.last_error === "budget" && " · paused: AI budget used up this month"}
          {b.last_error === "needs_reauth" && " · paused: reconnect the mailbox"}
        </p>
      </div>
      <div className="flex gap-2">
        {b.status === "running" && <Button size="sm" variant="secondary" onClick={() => act("pause")}><Pause aria-hidden="true" /> Pause</Button>}
        {b.status === "paused" && <Button size="sm" variant="secondary" onClick={() => act("resume")}><Play aria-hidden="true" /> Resume</Button>}
        {["running", "paused"].includes(b.status) && <Button size="sm" variant="ghost" onClick={() => act("cancel")}><X aria-hidden="true" /> Cancel</Button>}
      </div>
    </div>
  );
}

function SourcesPage() {
  const params = useSearchParams();
  const accounts = useApi<{ items: Account[]; triage_local: boolean; oauth?: Oauth; connection?: Connection }>("/api/sources/accounts");
  const backfills = useApi<{ items: Backfill[] }>("/api/sources/backfills");
  const [status, setStatus] = React.useState("");
  const log = useApi<{ items: Msg[] }>(`/api/sources/messages?limit=50${status ? `&status=${status}` : ""}`);
  const [connect, setConnect] = React.useState(params.get("connect"));
  const connectedId = Number(params.get("connected"));
  const [range, setRange] = React.useState<{ account: number; from: string; to: string } | null>(
    Number.isSafeInteger(connectedId) && connectedId > 0 ? { account: connectedId, from: daysAgo(30), to: daysAgo(0) } : null,
  );
  const [notice, setNotice] = React.useState(params.get("connected") ? "Mailbox connected. New attachments will be checked automatically. Choose a range below to import older documents." : "");
  const [importing, setImporting] = React.useState(false);
  const [error, setError] = React.useState<ApiError | null>(null);
  const running = backfills.data?.items.some((b) => b.status === "running");
  const watching = accounts.data?.items.some((a) => a.status === "active");
  const showConnect = connect !== null || (!accounts.loading && !accounts.error && accounts.data?.items.length === 0);

  const { reload: reloadAccounts } = accounts;
  const { reload: reloadBackfills } = backfills;
  const { reload: reloadLog } = log;
  React.useEffect(() => {
    if (!running && !watching) return;
    const t = setInterval(() => { reloadBackfills(); reloadLog(); reloadAccounts(); }, 10000);
    return () => clearInterval(t);
  }, [running, watching, reloadBackfills, reloadLog, reloadAccounts]);

  const call = (p: Promise<unknown>, after: () => void) =>
    p.then(after).catch((e: ApiError) => setError(e));

  return (
    <Page>
      <PageHeader title="Sources" description="Automatically collect invoices, statements and other document attachments from your email."
        actions={<Button onClick={() => setConnect("choose")}><Mail aria-hidden="true" /> Connect a mailbox</Button>} />
      {notice && <p role="status" className="mb-4 rounded border border-success bg-surface p-3">{notice}</p>}
      {params.get("error") && <ErrorBox error={new Error(params.get("message") || "Connecting the mailbox did not work. Try again.")} />}
      {error && <div className="mb-4"><ErrorBox error={error} /></div>}

      {showConnect && (
        <Card title="Connect a mailbox" className="mb-4" actions={accounts.data?.items.length ? <Button size="sm" variant="ghost" onClick={() => setConnect(null)}>Close</Button> : undefined}>
          <ul className="mb-4 space-y-1 text-sm text-text-muted">
            <li className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="size-4 shrink-0 text-success" /> Read-only access: DocuHive never sends, moves or deletes email.</li>
            <li className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="size-4 shrink-0 text-success" /> Only attachments that look like documents are imported.</li>
            {accounts.data && !accounts.data.triage_local && (
              <li className="flex items-center gap-2 text-warning"><Badge tone="warn">Cloud</Badge> Email sender, subject and a short text snippet are checked by a cloud model. Set a local triage model in Settings → AI to keep them on this server.</li>
            )}
          </ul>
          {accounts.error ? <ErrorBox error={accounts.error} onRetry={accounts.reload} /> : accounts.loading && !accounts.data ? <Skeleton rows={3} /> : <ConnectMailbox initial={connect || "choose"} oauth={accounts.data?.oauth} connection={accounts.data?.connection} onDone={(account) => {
            setConnect(null); accounts.reload();
            setRange({ account: account.id, from: daysAgo(30), to: daysAgo(0) });
            setNotice(`${account.address} connected. New attachments will be checked automatically. Choose a range below to import older documents.`);
          }} />}
          <p className="mt-4 text-xs text-text-muted">Checks for new mail every {accounts.data?.connection?.sync_every_min ?? 15} minutes. Existing documents are skipped automatically.</p>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Mailboxes">
          {accounts.loading && !accounts.data ? <Skeleton rows={2} /> : accounts.error ? <ErrorBox error={accounts.error} onRetry={accounts.reload} /> :
            !accounts.data?.items.length ? <p className="text-sm text-text-muted">Your connected mailboxes will appear here. Choose a provider above to get started.</p> : (
              <ul className="divide-y divide-border">
                {accounts.data.items.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">{a.display_name || a.address}</span>
                        <Badge tone={STATUS_TONE[a.status]}>{STATUS_TEXT[a.status] ?? a.status}</Badge>
                      </div>
                      <p className="text-xs text-text-muted">{PROVIDER[a.provider]} · {a.address} · last check {a.last_sync_at ? formatDate(a.last_sync_at) : "queued"}</p>
                    </div>
                    <div className="flex gap-2">
                      {a.status === "needs_reauth" ? (
                        <Button size="sm" asChild><a href={`/api/sources/oauth/${a.provider === "gmail" ? "google" : "microsoft"}/start`}>Reconnect</a></Button>
                      ) : (
                        <>
                          <Button size="sm" variant="secondary" aria-label={`Sync ${a.address} now`} onClick={() => call(api(`/api/sources/accounts/${a.id}/sync`, { method: "POST" }), accounts.reload)}><RefreshCw aria-hidden="true" /></Button>
                          <Button size="sm" variant="secondary" onClick={() => call(api(`/api/sources/accounts/${a.id}`, { method: "PATCH", json: { paused: a.status !== "paused" } }), accounts.reload)}>
                            {a.status === "paused" ? "Resume" : "Pause"}
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => setRange({ account: a.id, from: daysAgo(30), to: daysAgo(0) })}>
                            <History aria-hidden="true" /> Import history
                          </Button>
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          {range && (
            <form className="mt-4 space-y-3 rounded border border-border p-3" onSubmit={(e) => {
              e.preventDefault();
              if (importing) return;
              setImporting(true);
              setError(null);
              call(api(`/api/sources/accounts/${range.account}/backfills`, { method: "POST", json: { date_from: range.from, date_to: range.to } }),
                () => { setRange(null); backfills.reload(); setNotice("History import started. You can leave this page; documents will appear in your archive as they are processed."); }).finally(() => setImporting(false));
            }}>
              <h3 className="font-semibold">Import existing attachments</h3>
              <p className="text-sm text-text-muted">Choose how far back to look in {accounts.data?.items.find((a) => a.id === range.account)?.address || "your connected mailbox"}. Only document attachments are imported.</p>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map((p) => (
                  <Button key={p.label} type="button" size="sm" variant="secondary"
                    onClick={() => setRange({ ...range, from: p.days ? daysAgo(p.days) : p.since ?? isoDaysAgo(p.years!) })}>{p.label}</Button>
                ))}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="From"><Input required type="date" max={range.to} value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></Field>
                <Field label="To"><Input required type="date" min={range.from} max={daysAgo(0)} value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></Field>
              </div>
              <p className="text-xs text-text-muted">Runs in the background and can be paused. Documents already archived are skipped.</p>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="secondary" disabled={importing} onClick={() => setRange(null)}>Skip for now</Button>
                <Button type="submit" disabled={importing}>{importing ? "Starting import…" : "Import attachments"}</Button>
              </div>
            </form>
          )}
        </Card>
        <Card title="History imports">
          {backfills.loading && !backfills.data ? <Skeleton rows={2} /> : backfills.error ? <ErrorBox error={backfills.error} onRetry={backfills.reload} /> : backfills.data?.items.length ? (
            <div className="space-y-2">{backfills.data.items.map((b) => <BackfillCard key={b.id} b={b} onChange={backfills.reload} onError={setError} />)}</div>
          ) : <p className="text-sm text-text-muted">None yet. Use “Import history” on a mailbox to bring in older documents.</p>}
        </Card>
      </div>

      <Card title="Email activity" className="mt-4" actions={
        <select aria-label="Filter by status" className={`${controlSm} !w-48 max-w-full`} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All messages</option>
          {["imported", "partial", "triage_rejected", "prefiltered_out", "error"].map((s) => <option key={s} value={s}>{STATUS_TEXT[s] ?? "Failed"}</option>)}
        </select>}>
        {log.loading && !log.data ? <Skeleton rows={5} /> : log.error ? <ErrorBox error={log.error} onRetry={log.reload} /> : !log.data?.items.length ? <p className="text-sm text-text-muted">No email processed yet.</p> : (
          <ul className="divide-y divide-border">
            {log.data.items.map((m) => (
              <li key={m.id}>
                <details className="py-2">
                  <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2">
                    <span className="min-w-0 truncate"><span className="font-medium">{m.subject || "(no subject)"}</span> <span className="text-xs text-text-muted">{m.email_from}</span></span>
                    <span className="flex items-center gap-2">
                      <span className="tabular text-xs text-text-muted">{formatDate(m.received_at)}</span>
                      <Badge tone={STATUS_TONE[m.status] ?? "error"}>{STATUS_TEXT[m.status] ?? "Failed"}</Badge>
                    </span>
                  </summary>
                  <div className="mt-2 space-y-2 pl-4 text-sm">
                    {m.reason && <p className="text-text-muted">Why: {m.reason.replace(/^prefilter:/, "rule: ")}</p>}
                    {m.attachments.map((a, i) => (
                      <p key={i}>{a.document_id ? <Link className="hover:underline" href={`/documents/${a.document_id}`}>{a.filename}</Link> : a.filename} · {a.status}</p>
                    ))}
                    {["triage_rejected", "prefiltered_out"].includes(m.status) && (
                      <Button size="sm" variant="secondary" onClick={() => call(api(`/api/sources/messages/${m.id}/import`, { method: "POST" }), log.reload)}>Import anyway</Button>
                    )}
                  </div>
                </details>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  );
}

export default function SourcesRoute() {
  return (
    <React.Suspense fallback={<Page><Skeleton rows={6} /></Page>}>
      <SourcesPage />
    </React.Suspense>
  );
}
