"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, RefreshCw, Search, ShieldCheck, Store } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { control } from "@/lib/ui/control";
import {
  api,
  ApiError,
  Badge,
  Card,
  Empty,
  ErrorBox,
  Skeleton,
  useApi,
} from "@/components/intel/common";

export type Entry = {
  id: string;
  name: string;
  description: string;
  labels: string[];
  version: string | null;
  capabilities: { id: string; label: string }[];
  installed_version: string | null;
  state: "available" | "installed" | "update" | "problem";
  message: string | null;
};

const STATE = {
  available: null,
  installed: { tone: "ok", label: "Installed" },
  update: { tone: "info", label: "Update available" },
  problem: { tone: "error", label: "Cannot be installed" },
} as const;

/** The plugins shipped with DocuHive: find one, see what it may do, install it. */
export function Marketplace({
  onInstalled,
  onOpen,
}: {
  onInstalled: () => void;
  onOpen: (id: string) => void;
}) {
  const list = useApi<Entry[]>("/api/plugins/catalogue");
  const [query, setQuery] = useState("");
  const [label, setLabel] = useState("");
  const labels = useMemo(
    () => [...new Set((list.data ?? []).flatMap((e) => e.labels))].sort(),
    [list.data],
  );
  const shown = (list.data ?? []).filter(
    (e) =>
      (!label || e.labels.includes(label)) &&
      `${e.name} ${e.description} ${e.labels.join(" ")}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );
  if (list.error) return <ErrorBox error={list.error} onRetry={list.reload} />;
  if (list.loading && !list.data) return <Skeleton rows={4} />;
  if (!list.data?.length)
    return (
      <Empty
        icon={Store}
        text="The marketplace is empty: this installation has no catalogue of plugins (DOCUHIVE_CATALOGUE_DIR)."
      />
    );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <label className="relative min-w-48 flex-1">
          <span className="sr-only">Search plugins</span>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-subtle"
          />
          <Input
            type="search"
            className="pl-9"
            placeholder="Search plugins"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="w-48">
          <span className="sr-only">For</span>
          <select
            className={control}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          >
            <option value="">All plugins</option>
            {labels.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!shown.length ? (
        <Empty
          icon={Search}
          text="No plugin matches. Clear the search or choose All plugins."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {shown.map((e) => (
            <Offer
              key={e.id}
              entry={e}
              onChange={() => {
                list.reload();
                onInstalled();
              }}
              onOpen={onOpen}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Offer({
  entry: e,
  onChange,
  onOpen,
}: {
  entry: Entry;
  onChange: () => void;
  onOpen: (id: string) => void;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState("");
  const state = STATE[e.state];

  async function run(work: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await work();
      setNotice(done);
      setConfirming(false);
      onChange();
      router.refresh(); // its pages appear in the sidebar
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  const install = (switchOn: boolean) =>
    run(
      async () => {
        await api(`/api/plugins/catalogue/${e.id}/install`, { method: "POST" });
        if (switchOn)
          await api(`/api/plugins/${e.id}/enable`, {
            method: "POST",
            json: { capabilities: e.capabilities.map((c) => c.id) },
          });
      },
      switchOn
        ? `${e.name} is on. Its pages are in the sidebar.`
        : `${e.name} is installed. Switch it on under Installed.`,
    );

  return (
    <Card
      title={e.name}
      actions={
        state && (
          <Badge tone={state.tone}>
            {state.label}
            {e.version && (
              <span className="text-text-muted"> · {e.version}</span>
            )}
          </Badge>
        )
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm">{e.description}</p>
        {e.labels.length > 0 && (
          <ul className="flex flex-wrap gap-1" aria-label="Labels">
            {e.labels.map((l) => (
              <li
                key={l}
                className="rounded-md border border-border px-2 text-xs leading-5 text-text-muted"
              >
                {l}
              </li>
            ))}
          </ul>
        )}
        {e.message && <p className="text-xs text-text-muted">{e.message}</p>}
        <details className="text-sm">
          <summary className="flex cursor-pointer items-center gap-2 font-medium">
            <ShieldCheck aria-hidden="true" className="size-4" />
            What it may do
          </summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-6">
            {e.capabilities.length ? (
              e.capabilities.map((c) => <li key={c.id}>{c.label}</li>)
            ) : (
              <li>Nothing beyond adding document types</li>
            )}
          </ul>
        </details>
        {confirming && (
          <div
            role="dialog"
            aria-label={`Install ${e.name}`}
            className="space-y-3 rounded-card border border-warning p-4"
          >
            <p className="text-sm">{e.name} may:</p>
            <ul className="list-disc space-y-0.5 pl-6 text-sm">
              {e.capabilities.map((c) => (
                <li key={c.id}>{c.label}</li>
              ))}
            </ul>
            <p className="text-sm">
              A plugin runs inside DocuHive with access to your documents.
              Switch it on only if you agree with this list.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => void install(true)}>
                Install and switch on
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void install(false)}
              >
                Install only
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
        {error && <ErrorBox error={error} />}
        {notice && (
          <p role="status" className="text-sm text-text-muted">
            {notice}
          </p>
        )}
        {!confirming && (
          <div className="flex flex-wrap gap-2">
            {e.state === "available" && (
              <Button disabled={busy} onClick={() => setConfirming(true)}>
                <Download aria-hidden="true" /> Install
              </Button>
            )}
            {e.state === "update" && (
              <Button
                disabled={busy}
                onClick={() =>
                  void run(
                    () =>
                      api(`/api/plugins/${e.id}/update`, { method: "POST" }),
                    `Updated to ${e.version}. Your own files are kept.`,
                  )
                }
              >
                <RefreshCw aria-hidden="true" /> Update to {e.version}
              </Button>
            )}
            {(e.state === "installed" || e.state === "update") && (
              <Button variant="secondary" onClick={() => onOpen(e.id)}>
                Settings
              </Button>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
