"use client";

import * as React from "react";
import { Bell, Send, Trash2 } from "lucide-react";
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

type Channel = { id: number; kind: string; enabled: boolean; config: Record<string, unknown> };
type LogRow = { id: number; at: string; kind: string; title: string; ok: boolean; error: string | null };
const KIND_LABEL: Record<string, string> = {
  reminder: "Deadline reminders", quarantine: "Documents that failed", job_dead: "Failed background jobs",
  review_backlog: "Review backlog", mail_reauth: "Mailbox needs reconnecting", budget: "AI budget", backup: "Backups",
};

function ChannelForm({ onDone }: { onDone: () => void }) {
  const [kind, setKind] = React.useState<"ntfy" | "email">("ntfy");
  const [cfg, setCfg] = React.useState<Record<string, string>>({ server: "https://ntfy.sh", topic: "", port: "587" });
  const [error, setError] = React.useState<ApiError | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setCfg({ ...cfg, [k]: e.target.value });
  return (
    <form className="space-y-4" onSubmit={async (e) => {
      e.preventDefault();
      const ok = await api("/api/notifications/channels", { method: "POST", json: { kind, config: cfg } })
        .then(() => true).catch((err) => (setError(err), false));
      if (ok) onDone();
    }}>
      <div className="flex gap-2" role="radiogroup" aria-label="Channel type">
        {(["ntfy", "email"] as const).map((k) => (
          <Button key={k} type="button" variant={kind === k ? "primary" : "secondary"} role="radio" aria-checked={kind === k} onClick={() => setKind(k)}>
            {k === "ntfy" ? "Phone push (ntfy)" : "Email"}
          </Button>
        ))}
      </div>
      {kind === "ntfy" ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Server" help="ntfy.sh or your own ntfy server"><Input required value={cfg.server ?? ""} onChange={set("server")} /></Field>
          <Field label="Topic" help="Pick a long, hard-to-guess topic name"><Input required value={cfg.topic ?? ""} onChange={set("topic")} /></Field>
          <Field label="Access token (optional)"><Input type="password" value={cfg.token ?? ""} onChange={set("token")} /></Field>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="SMTP server"><Input required value={cfg.host ?? ""} onChange={set("host")} /></Field>
          <Field label="Port"><Input required inputMode="numeric" value={cfg.port ?? ""} onChange={set("port")} /></Field>
          <Field label="User name"><Input autoComplete="username" value={cfg.username ?? ""} onChange={set("username")} /></Field>
          <Field label="Password"><Input type="password" autoComplete="current-password" value={cfg.password ?? ""} onChange={set("password")} /></Field>
          <Field label="From address"><Input required type="email" value={cfg.from ?? ""} onChange={set("from")} /></Field>
          <Field label="Send to"><Input required type="email" value={cfg.to ?? ""} onChange={set("to")} /></Field>
        </div>
      )}
      {error && <ErrorBox error={error} />}
      <div className="flex justify-end"><Button type="submit">Add channel</Button></div>
    </form>
  );
}

export default function NotificationsPage() {
  const channels = useApi<{ items: Channel[]; kinds: string[] }>("/api/notifications/channels");
  const log = useApi<{ items: LogRow[] }>("/api/notifications/log");
  const [adding, setAdding] = React.useState(false);
  const [result, setResult] = React.useState<Record<number, string>>({});
  const [error, setError] = React.useState<ApiError | null>(null);

  async function toggleKind(c: Channel, kind: string) {
    const all = channels.data?.kinds ?? [];
    const current = (c.config.kinds as string[] | undefined) ?? all;
    const kinds = current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind];
    await api(`/api/notifications/channels/${c.id}`, { method: "PATCH", json: { kinds } }).then(channels.reload).catch(setError);
  }

  return (
    <Page narrow>
      <PageHeader title="Notifications" description="Where DocuHive tells you about deadlines and problems. Messages never contain document content."
        actions={!adding && <Button onClick={() => setAdding(true)}><Bell aria-hidden="true" /> Add channel</Button>} />
      {error && <div className="mb-4"><ErrorBox error={error} /></div>}
      {adding && <Card title="New channel" className="mb-4"><ChannelForm onDone={() => { setAdding(false); channels.reload(); }} /></Card>}
      {channels.loading && !channels.data ? <Skeleton rows={3} /> : channels.error ? <ErrorBox error={channels.error} onRetry={channels.reload} /> :
        !channels.data?.items.length ? (
          !adding && <Empty icon={Bell} text="No channel yet. Add phone push or email to get deadline reminders." action={<Button onClick={() => setAdding(true)}>Add channel</Button>} />
        ) : (
          <div className="space-y-4">
            {channels.data.items.map((c) => (
              <Card key={c.id} title={c.kind === "ntfy" ? `Push: ${c.config.topic}` : c.kind === "email" ? `Email: ${c.config.to}` : c.kind}
                actions={<div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={async () => {
                    const r = await api<{ ok: boolean; error: string | null }>(`/api/notifications/channels/${c.id}/test`, { method: "POST" }).catch((e) => ({ ok: false, error: e.message }));
                    setResult({ ...result, [c.id]: r.ok ? "Test sent. Check your phone or inbox." : `Test failed: ${r.error}` });
                    log.reload();
                  }}><Send aria-hidden="true" /> Send test</Button>
                  <Button size="sm" variant="ghost" aria-label="Delete channel" onClick={() => api(`/api/notifications/channels/${c.id}`, { method: "DELETE" }).then(channels.reload).catch(setError)}><Trash2 aria-hidden="true" /></Button>
                </div>}>
                {result[c.id] && <p role="status" className="mb-3 text-sm">{result[c.id]}</p>}
                <fieldset>
                  <legend className="mb-2 text-sm font-medium">Send me</legend>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {channels.data!.kinds.map((k) => {
                      const on = !c.config.kinds || (c.config.kinds as string[]).includes(k);
                      return (
                        <label key={k} className="flex items-center gap-2 text-sm">
                          <input type="checkbox" className="size-4" checked={on} onChange={() => toggleKind(c, k)} />
                          {KIND_LABEL[k] ?? k}
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
              </Card>
            ))}
          </div>
        )}
      <Card title="Recently sent" className="mt-4">
        {!log.data?.items.length ? <p className="text-sm text-text-muted">Nothing sent yet.</p> : (
          <ul className="divide-y divide-border text-sm">
            {log.data.items.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="min-w-0 truncate">{r.title}</span>
                <span className="flex items-center gap-2">
                  <span className="tabular text-xs text-text-muted">{formatDate(r.at)}</span>
                  <Badge tone={r.ok ? "ok" : "error"}>{r.ok ? "Sent" : r.error === "no enabled channel" ? "No channel" : "Failed"}</Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  );
}
