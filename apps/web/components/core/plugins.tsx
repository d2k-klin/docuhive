"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Power, Puzzle, ShieldCheck, Trash2 } from "lucide-react";
import { Marketplace } from "@/components/core/marketplace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox, control } from "@/lib/ui/control";
import {
  api,
  ApiError,
  Badge,
  Card,
  Empty,
  ErrorBox,
  Field,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type Setting = {
  key: string;
  type:
    "string" | "number" | "boolean" | "date" | "choice" | "secret" | "profile";
  label: string;
  help: string;
  required: boolean;
  options: string[];
};
type Plugin = {
  id: string;
  name: string;
  description: string;
  version: string | null;
  source: string;
  enabled: boolean;
  running: boolean;
  state: "on" | "off" | "problem" | "needs_approval" | "needs_restart";
  message: string | null;
  capabilities: { id: string; label: string }[];
  settings: Setting[];
  values: Record<string, unknown>;
  in_ask?: boolean | null;
};

const STATE: Record<
  Plugin["state"],
  { tone: "ok" | "muted" | "error" | "warn" | "info"; label: string }
> = {
  on: { tone: "ok", label: "On" },
  off: { tone: "muted", label: "Off" },
  problem: { tone: "error", label: "Could not start" },
  needs_approval: { tone: "warn", label: "Needs your approval" },
  needs_restart: { tone: "info", label: "Starting" },
};

/** Settings → Plugins: the installed ones (switch on and off, settings) and the marketplace of
 * plugins shipped with DocuHive, to install with one click. Changes apply without a restart. */
export function Plugins({
  initialTab = "installed",
}: {
  initialTab?: "installed" | "marketplace";
}) {
  const list = useApi<Plugin[]>("/api/plugins");
  const [tab, setTab] = useState(initialTab);
  const replace = (p: Plugin) =>
    list.setData((all) => all && all.map((x) => (x.id === p.id ? p : x)));
  const open = (id: string) => {
    setTab("installed");
    window.location.hash = id;
  };
  const tabs = [
    {
      id: "installed",
      label: `Installed${list.data ? ` (${list.data.length})` : ""}`,
    },
    { id: "marketplace", label: "Marketplace" },
  ] as const;
  return (
    <Page narrow>
      <PageHeader
        title="Plugins"
        description="Plugins make your documents do a job, such as tax returns or contract reminders. Only an administrator can install them and switch them on."
      />
      <div role="tablist" aria-label="Plugins" className="mb-4 flex gap-2">
        {tabs.map((t) => (
          <Button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            variant={tab === t.id ? "secondary" : "ghost"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </Button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "marketplace" ? (
          <Marketplace onInstalled={list.reload} onOpen={open} />
        ) : list.error ? (
          <ErrorBox error={list.error} onRetry={list.reload} />
        ) : list.loading && !list.data ? (
          <Skeleton rows={4} />
        ) : !list.data?.length ? (
          <Empty
            icon={Puzzle}
            text="No plugins installed yet."
            action={
              <Button onClick={() => setTab("marketplace")}>
                Browse the marketplace
              </Button>
            }
          />
        ) : (
          <div className="space-y-4">
            {list.data.map((p) => (
              <PluginCard
                key={p.id}
                plugin={p}
                onChange={replace}
                onRemoved={list.reload}
              />
            ))}
          </div>
        )}
      </div>
    </Page>
  );
}

function PluginCard({
  plugin: p,
  onChange,
  onRemoved,
}: {
  plugin: Plugin;
  onChange: (p: Plugin) => void;
  onRemoved: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const state = STATE[p.state];
  const router = useRouter();
  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/plugins/${p.id}`, { method: "DELETE" });
      onRemoved();
      router.refresh();
    } catch (e) {
      setError(e as ApiError);
      setBusy(false);
    }
  }
  async function call(action: "enable" | "disable") {
    setBusy(true);
    setError(null);
    try {
      onChange(
        await api<Plugin>(`/api/plugins/${p.id}/${action}`, {
          method: "POST",
          json:
            action === "enable"
              ? { capabilities: p.capabilities.map((c) => c.id) }
              : undefined,
        }),
      );
      setConfirming(false);
      router.refresh(); // its pages appear in, or leave, the sidebar
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }
  async function setInAsk(use: boolean) {
    setBusy(true);
    setError(null);
    try {
      onChange(
        await api<Plugin>(`/api/plugins/${p.id}/ask`, {
          method: "PUT",
          json: { use },
        }),
      );
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section id={p.id} className="scroll-mt-4">
      <Card
        title={p.name}
        actions={
          <Badge tone={state.tone}>
            {state.label}
            {p.version && (
              <span className="text-text-muted"> · {p.version}</span>
            )}
          </Badge>
        }
      >
        <div className="space-y-4">
          {p.description && <p className="text-sm">{p.description}</p>}
          {p.message && (
            <p
              role={p.state === "problem" ? "alert" : undefined}
              className="text-sm text-text-muted"
            >
              {p.message}
            </p>
          )}
          <div>
            <p className="mb-1 flex items-center gap-2 text-sm font-medium">
              <ShieldCheck aria-hidden="true" className="size-4" />
              What it may do
            </p>
            {p.capabilities.length ? (
              <ul className="list-disc space-y-0.5 pl-6 text-sm">
                {p.capabilities.map((c) => (
                  <li key={c.id}>{c.label}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-text-muted">
                Nothing beyond adding document types.
              </p>
            )}
          </div>
          {confirming && (
            <div
              role="dialog"
              aria-label={`Switch ${p.name} on`}
              className="space-y-3 rounded-card border border-warning p-4"
            >
              <p className="text-sm">
                A plugin runs inside DocuHive with access to your documents.
                Switch it on only if you trust where it comes from and you agree
                with the list above.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button disabled={busy} onClick={() => void call("enable")}>
                  Switch on
                </Button>
                <Button variant="ghost" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {error && <ErrorBox error={error} />}
          {!confirming && (
            <div className="flex flex-wrap gap-2">
              {p.enabled && p.state !== "needs_approval" ? (
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void call("disable")}
                >
                  <Power aria-hidden="true" /> Switch off
                </Button>
              ) : (
                <Button
                  disabled={busy || p.state === "problem"}
                  onClick={() => setConfirming(true)}
                >
                  <Power aria-hidden="true" />
                  {p.state === "needs_approval"
                    ? "Review and approve"
                    : "Switch on"}
                </Button>
              )}
              {!p.enabled && p.source === "folder" && (
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Remove ${p.name}? Its documents, data and settings stay, and come back if you install it again.`,
                      )
                    )
                      void remove();
                  }}
                >
                  <Trash2 aria-hidden="true" /> Remove
                </Button>
              )}
            </div>
          )}
          {p.enabled && (
            <p className="text-xs text-text-muted">
              Switching off removes its screens and jobs. Its documents and data
              stay, and come back when you switch it on again.
            </p>
          )}
          {p.in_ask != null && (
            <label className="flex min-h-5 items-start gap-2 text-sm">
              <input
                type="checkbox"
                className={checkbox}
                checked={p.in_ask}
                disabled={busy}
                onChange={(e) => void setInAsk(e.target.checked)}
              />
              <span>
                <span className="font-medium">Use in Ask</span>
                <span className="block text-xs text-text-muted">
                  Ask may look up this plugin&apos;s records to answer
                  questions, within the same privacy rules as documents.
                </span>
              </span>
            </label>
          )}
          {p.settings.length > 0 && (
            <SettingsForm plugin={p} onChange={onChange} />
          )}
        </div>
      </Card>
    </section>
  );
}

function SettingsForm({
  plugin: p,
  onChange,
}: {
  plugin: Plugin;
  onChange: (p: Plugin) => void;
}) {
  const initial = () =>
    Object.fromEntries(
      p.settings.map((s) => [
        s.key,
        s.type === "secret"
          ? ""
          : (p.values[s.key] ?? (s.type === "boolean" ? false : "")),
      ]),
    );
  const [values, setValues] = useState<Record<string, unknown>>(initial);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch(`/api/plugins/${p.id}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-DocuHive-CSRF": "1" },
        body: JSON.stringify(values),
      });
      const body = await res.json();
      if (!res.ok) {
        setFieldErrors(body.error?.details?.fields ?? {});
        throw new ApiError(body.error?.code, body.error?.message, res.status);
      }
      setFieldErrors({});
      setValues(
        Object.fromEntries(
          Object.entries(values).map(([k, v]) =>
            p.settings.find((s) => s.key === k)?.type === "secret"
              ? [k, ""]
              : [k, v],
          ),
        ),
      );
      onChange(body as Plugin);
      setSaved(true);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }
  const set = (key: string, value: unknown) =>
    setValues((all) => ({ ...all, [key]: value }));
  return (
    <form onSubmit={save} className="space-y-4 border-t border-border pt-4">
      <h3 className="font-semibold">Settings</h3>
      {p.settings.map((s) => {
        const id = `${p.id}-${s.key}`;
        const problem = fieldErrors[s.key];
        const savedSecret =
          s.type === "secret" &&
          (p.values[s.key] as { saved?: boolean } | undefined)?.saved;
        if (s.type === "boolean")
          return (
            <label key={s.key} className="flex min-h-5 items-center gap-2">
              <input
                id={id}
                type="checkbox"
                className={checkbox}
                checked={Boolean(values[s.key])}
                onChange={(e) => set(s.key, e.target.checked)}
              />
              {s.label}
            </label>
          );
        const help = [
          s.help,
          savedSecret ? "Saved. Leave empty to keep it." : "",
          problem,
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <Field
            key={s.key}
            label={s.label + (s.required ? " (required)" : "")}
            help={help}
          >
            {s.type === "choice" ? (
              <select
                id={id}
                className={control}
                aria-invalid={Boolean(problem)}
                value={String(values[s.key] ?? "")}
                onChange={(e) => set(s.key, e.target.value)}
              >
                <option value="">Choose…</option>
                {s.options.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : (
              <Input
                id={id}
                aria-invalid={Boolean(problem)}
                type={
                  s.type === "secret"
                    ? "password"
                    : s.type === "date"
                      ? "date"
                      : s.type === "number"
                        ? "number"
                        : "text"
                }
                autoComplete={s.type === "secret" ? "new-password" : "off"}
                value={String(values[s.key] ?? "")}
                onChange={(e) => set(s.key, e.target.value)}
              />
            )}
          </Field>
        );
      })}
      {error && <ErrorBox error={error} />}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="secondary" disabled={busy}>
          {busy ? "Saving…" : "Save settings"}
        </Button>
        {saved && (
          <span role="status" className="text-sm text-text-muted">
            Saved.
          </span>
        )}
      </div>
    </form>
  );
}
