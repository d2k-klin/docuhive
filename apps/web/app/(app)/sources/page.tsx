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
  Empty,
  ErrorBox,
  Field,
  formatDate,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";
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
  { label: "Last year", years: 1 },
  { label: "Last 3 years", years: 3 },
  { label: "Since 2015", since: "2015-01-01" },
];

function isoDaysAgo(years: number) {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
}

function ImapForm({ onDone }: { onDone: () => void }) {
  const [f, setF] = React.useState({ host: "", port: "993", username: "", password: "", folders: "INBOX" });
  const [error, setError] = React.useState<ApiError | null>(null);
  const [busy, setBusy] = React.useState(false);
  return (
    <form className="grid gap-4 md:grid-cols-2" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      setError(null);
      const ok = await api("/api/sources/accounts", { method: "POST", json: {
        provider: "imap", host: f.host, port: Number(f.port), username: f.username, password: f.password,
        folders: f.folders.split(",").map((x) => x.trim()).filter(Boolean),
      } }).then(() => true).catch((err) => (setError(err), false));
      setBusy(false);
      if (ok) onDone();
    }}>
      <Field label="Server"><Input required placeholder="imap.example.org" value={f.host} onChange={(e) => setF({ ...f, host: e.target.value })} /></Field>
      <Field label="Port"><Input required inputMode="numeric" value={f.port} onChange={(e) => setF({ ...f, port: e.target.value })} /></Field>
      <Field label="User name"><Input required autoComplete="username" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
      <Field label="App password" help="Use an app password, not your main password. It is stored encrypted.">
        <Input required type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
      </Field>
      <Field label="Folders" help="Comma-separated, e.g. INBOX, Rechnungen"><Input value={f.folders} onChange={(e) => setF({ ...f, folders: e.target.value })} /></Field>
      <div className="flex items-end justify-end gap-2">
        <Button type="submit" disabled={busy}>{busy ? "Testing login…" : "Test and connect"}</Button>
      </div>
      {error && <div className="md:col-span-2"><ErrorBox error={error} /></div>}
    </form>
  );
}

function BackfillCard({ b, onChange }: { b: Backfill; onChange: () => void }) {
  const act = (action: string) => api(`/api/sources/backfills/${b.id}/${action}`, { method: "POST" }).then(onChange);
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
  const accounts = useApi<{ items: Account[]; triage_local: boolean }>("/api/sources/accounts");
  const backfills = useApi<{ items: Backfill[] }>("/api/sources/backfills");
  const [status, setStatus] = React.useState("");
  const log = useApi<{ items: Msg[] }>(`/api/sources/messages?limit=50${status ? `&status=${status}` : ""}`);
  const [connect, setConnect] = React.useState(params.get("connect"));
  const [range, setRange] = React.useState<{ account: number; from: string; to: string } | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const running = backfills.data?.items.some((b) => b.status === "running");

  React.useEffect(() => {
    if (!running) return;
    const t = setInterval(backfills.reload, 5000);
    return () => clearInterval(t);
  }, [running, backfills.reload]);

  const call = (p: Promise<unknown>, after: () => void) =>
    p.then(after).catch((e: ApiError) => setError(e));

  return (
    <Page>
      <PageHeader title="Sources" description="Mailboxes DocuHive reads documents from. Nothing in your mailbox is changed or deleted."
        actions={<Button onClick={() => setConnect("choose")}><Mail aria-hidden="true" /> Connect a mailbox</Button>} />
      {params.get("connected") && <p role="status" className="mb-4 text-success">Mailbox connected. The first sync has started.</p>}
      {params.get("error") && <ErrorBox error={new Error(params.get("message") || "Connecting the mailbox did not work. Try again.")} />}
      {error && <div className="mb-4"><ErrorBox error={error} /></div>}

      {connect && (
        <Card title="Connect a mailbox" className="mb-4" actions={<Button size="sm" variant="ghost" onClick={() => setConnect(null)}>Close</Button>}>
          <ul className="mb-4 space-y-1 text-sm text-text-muted">
            <li className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="size-4 text-success" /> Read-only access: DocuHive never sends, moves or deletes email.</li>
            <li className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="size-4 text-success" /> Only attachments that look like documents are imported.</li>
            {accounts.data && !accounts.data.triage_local && (
              <li className="flex items-center gap-2 text-warning"><Badge tone="warn">Cloud</Badge> Email sender, subject and a short text snippet are checked by a cloud model. Set a local triage model in Settings → AI to keep them on this server.</li>
            )}
          </ul>
          <div className="mb-4 flex flex-wrap gap-2">
            {/* Full-page navigation on purpose: the API answers with a redirect to the provider. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <Button asChild><a href="/api/sources/oauth/google/start">Connect Gmail</a></Button>
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <Button asChild><a href="/api/sources/oauth/microsoft/start">Connect Outlook</a></Button>
            <Button variant="secondary" onClick={() => setConnect("imap")}>Other (IMAP)</Button>
          </div>
          {connect === "imap" && <ImapForm onDone={() => { setConnect(null); accounts.reload(); }} />}
          <p className="text-xs text-text-muted">Gmail and Outlook need a one-time app registration. See docs/setup/mail-accounts.md.</p>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Mailboxes">
          {accounts.loading && !accounts.data ? <Skeleton rows={2} /> : accounts.error ? <ErrorBox error={accounts.error} onRetry={accounts.reload} /> :
            !accounts.data?.items.length ? <Empty icon={Mail} text="No mailbox connected yet." action={<Button onClick={() => setConnect("choose")}>Connect a mailbox</Button>} /> : (
              <ul className="divide-y divide-border">
                {accounts.data.items.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">{a.display_name || a.address}</span>
                        <Badge tone={STATUS_TONE[a.status]}>{STATUS_TEXT[a.status] ?? a.status}</Badge>
                      </div>
                      <p className="text-xs text-text-muted">{PROVIDER[a.provider]} · {a.address} · last sync {a.last_sync_at ? formatDate(a.last_sync_at) : "never"}</p>
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
                          <Button size="sm" variant="secondary" onClick={() => setRange({ account: a.id, from: isoDaysAgo(1), to: new Date().toISOString().slice(0, 10) })}>
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
              call(api(`/api/sources/accounts/${range.account}/backfills`, { method: "POST", json: { date_from: range.from, date_to: range.to } }),
                () => { setRange(null); backfills.reload(); });
            }}>
              <h3 className="font-semibold">Import older email</h3>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map((p) => (
                  <Button key={p.label} type="button" size="sm" variant="secondary"
                    onClick={() => setRange({ ...range, from: p.since ?? isoDaysAgo(p.years!) })}>{p.label}</Button>
                ))}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="From"><Input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></Field>
                <Field label="To"><Input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></Field>
              </div>
              <p className="text-xs text-text-muted">Runs in the background and can be paused. Documents already archived are skipped.</p>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={() => setRange(null)}>Cancel</Button>
                <Button type="submit">Start import</Button>
              </div>
            </form>
          )}
        </Card>
        <Card title="History imports">
          {backfills.data?.items.length ? (
            <div className="space-y-2">{backfills.data.items.map((b) => <BackfillCard key={b.id} b={b} onChange={backfills.reload} />)}</div>
          ) : <p className="text-sm text-text-muted">None yet. Use “Import history” on a mailbox to bring in older documents.</p>}
        </Card>
      </div>

      <Card title="Triage log" className="mt-4" actions={
        <select aria-label="Filter by status" className={`${controlSm} w-48`} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All messages</option>
          {["imported", "partial", "triage_rejected", "prefiltered_out", "error"].map((s) => <option key={s} value={s}>{STATUS_TEXT[s] ?? "Failed"}</option>)}
        </select>}>
        {log.loading && !log.data ? <Skeleton rows={5} /> : !log.data?.items.length ? <p className="text-sm text-text-muted">No email processed yet.</p> : (
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
