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

type Oauth = { google: boolean; microsoft: boolean };
type Known = { name: string; domains: string[]; host?: string; oauth?: keyof Oauth; appPassword?: boolean; hint?: string; href?: string };

// Mail services whose IMAP server follows from the address. Outlook.com takes no IMAP passwords.
const KNOWN: Known[] = [
  { name: "Gmail", domains: ["gmail.com", "googlemail.com"], host: "imap.gmail.com", oauth: "google", appPassword: true,
    hint: "Gmail needs an app password, not your Google password. Turn on 2-Step Verification, then create one named DocuHive.",
    href: "https://myaccount.google.com/apppasswords" },
  { name: "Outlook", domains: ["outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.de", "hotmail.de"], oauth: "microsoft" },
  { name: "iCloud Mail", domains: ["icloud.com", "me.com", "mac.com"], host: "imap.mail.me.com", appPassword: true,
    hint: "iCloud needs an app-specific password from your Apple Account, not your Apple password.",
    href: "https://account.apple.com/account/manage" },
  { name: "Yahoo Mail", domains: ["yahoo.com", "yahoo.de"], host: "imap.mail.yahoo.com", appPassword: true,
    hint: "Yahoo needs an app password from your Yahoo account security settings." },
  { name: "GMX", domains: ["gmx.de", "gmx.net", "gmx.at", "gmx.ch"], host: "imap.gmx.net",
    hint: "Use your GMX password. Turn on POP3/IMAP access in the GMX settings first." },
  { name: "WEB.DE", domains: ["web.de"], host: "imap.web.de",
    hint: "Use your WEB.DE password. Turn on POP3/IMAP access in the WEB.DE settings first." },
  { name: "Posteo", domains: ["posteo.de", "posteo.net"], host: "posteo.de" },
  { name: "mailbox.org", domains: ["mailbox.org"], host: "imap.mailbox.org" },
  { name: "T-Online", domains: ["t-online.de", "magenta.de"], host: "secureimap.t-online.de",
    hint: "Use the separate password for e-mail programs from the T-Online e-mail settings." },
];

function known(address: string): Known | null {
  const domain = address.split("@")[1]?.trim().toLowerCase() ?? "";
  return KNOWN.find((k) => k.domains.includes(domain)) ?? null;
}

function ConnectForm({ oauth, onDone }: { oauth: Oauth | undefined; onDone: () => void }) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [advanced, setAdvanced] = React.useState(false);
  const [custom, setCustom] = React.useState({ host: "", port: "993", folders: "INBOX" });
  const [error, setError] = React.useState<ApiError | null>(null);
  const [busy, setBusy] = React.useState(false);
  const domain = email.includes("@") ? email.split("@")[1].trim().toLowerCase() : "";
  const service = known(email);
  const host = custom.host || service?.host || (domain ? `imap.${domain}` : "");
  const signIn = service?.oauth && oauth?.[service.oauth];

  if (service?.oauth === "microsoft") {
    return (
      <div className="space-y-3">
        <Field label="Email address"><Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        {signIn ? (
          /* eslint-disable-next-line @next/next/no-html-link-for-pages */
          <Button asChild><a href="/api/sources/oauth/microsoft/start">Sign in with Microsoft</a></Button>
        ) : (
          <p className="text-sm text-text-muted">Outlook.com only lets apps in through Microsoft sign-in, and that isn’t set up on this server yet. An administrator registers it once (docs/setup/mail-accounts.md).</p>
        )}
      </div>
    );
  }

  return (
    <form className="space-y-4" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      setError(null);
      const ok = await api("/api/sources/accounts", { method: "POST", json: {
        provider: "imap", host, port: Number(custom.port), username: email.trim(), password, address: email.trim(),
        folders: custom.folders.split(",").map((x) => x.trim()).filter(Boolean),
      } }).then(() => true).catch((err) => (setError(err), false));
      setBusy(false);
      if (ok) onDone();
    }}>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Email address"><Input required type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label={service?.appPassword ? "App password" : "Password"} help="Stored encrypted. DocuHive only reads mail; it never sends, moves or deletes.">
          <Input required type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
      </div>
      {service?.hint && (
        <p className="text-sm text-text-muted">
          {service.hint}{" "}
          {service.href && <a href={service.href} target="_blank" rel="noreferrer" className="text-primary underline">Open the page</a>}
        </p>
      )}
      {signIn && (
        <p className="text-sm">
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          Or <a href="/api/sources/oauth/google/start" className="text-primary underline">sign in with Google</a> instead.
        </p>
      )}
      {domain && !service && !advanced && (
        <p className="text-sm text-text-muted">Server: <span className="font-mono">{host}</span>. Not right? <button type="button" className="text-primary underline" onClick={() => setAdvanced(true)}>Change it</button></p>
      )}
      <details open={advanced} onToggle={(e) => setAdvanced((e.target as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer text-sm text-text-muted">Advanced: server, port and folders</summary>
        <div className="mt-3 grid gap-4 md:grid-cols-3">
          <Field label="Server"><Input placeholder={host || "imap.example.org"} value={custom.host} onChange={(e) => setCustom({ ...custom, host: e.target.value })} /></Field>
          <Field label="Port"><Input inputMode="numeric" value={custom.port} onChange={(e) => setCustom({ ...custom, port: e.target.value })} /></Field>
          <Field label="Folders" help="Comma-separated, e.g. INBOX, Rechnungen"><Input value={custom.folders} onChange={(e) => setCustom({ ...custom, folders: e.target.value })} /></Field>
        </div>
      </details>
      <div className="flex justify-end">
        <Button type="submit" disabled={busy || !host}>{busy ? "Checking the login…" : "Connect"}</Button>
      </div>
      {error && <ErrorBox error={error} />}
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
  const accounts = useApi<{ items: Account[]; triage_local: boolean; oauth?: Oauth }>("/api/sources/accounts");
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
          <ConnectForm oauth={accounts.data?.oauth} onDone={() => { setConnect(null); accounts.reload(); }} />
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
