"use client";

import { useCallback, useState } from "react";
import { KeyRound, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox as checkboxClass } from "@/lib/ui/control";

type Token = components["schemas"]["TokenView"];
type Scope = components["schemas"]["TokenCreate"]["scopes"][number];
const api = browserClient();
const scopeOptions: { id: Scope; label: string }[] = [
  { id: "upload", label: "Upload documents" },
  { id: "read", label: "Read documents and search" },
  { id: "write", label: "Read and edit documents" },
  { id: "kb:read", label: "Retrieve knowledge-base chunks" },
  { id: "kb:ask", label: "Ask knowledge bases" },
  { id: "calendar", label: "Calendar feed only" },
  { id: "admin", label: "All administrator actions" },
];

export function ApiTokens({
  admin,
  initialTokens,
}: {
  admin: boolean;
  initialTokens: Token[] | null;
}) {
  const [tokens, setTokens] = useState<Token[]>(initialTokens || []);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<Scope[]>(["kb:read"]);
  const [localConsumer, setLocalConsumer] = useState(false);
  const [secret, setSecret] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(
    initialTokens ? "" : "Your tokens could not be loaded. Try again.",
  );
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [revoking, setRevoking] = useState<number | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.GET("/api/tokens");
      if (!response.data) throw new Error();
      setTokens(response.data.items);
    } catch {
      setError("Your tokens could not be loaded. Try again.");
    } finally {
      setLoading(false);
    }
  }, []);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await api.POST("/api/tokens", {
        body: { name: name.trim(), scopes, local_consumer: localConsumer },
      });
      if (!response.data) throw new Error();
      setSecret(response.data.token);
      setCopied(false);
      setName("");
      await load();
    } catch {
      setError(
        "The token could not be created. Check its name and permissions, then try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: number) {
    setBusy(true);
    setError("");
    try {
      const response = await api.DELETE("/api/tokens/{token_id}", {
        params: { path: { token_id: id } },
      });
      if (!response.response.ok) throw new Error();
      setRevoking(null);
      await load();
    } catch {
      setError("The token could not be revoked. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header>
        <h1 className="text-xl font-semibold">API tokens</h1>
        <p className="text-sm text-text-muted">
          Give an app or agent only the access it needs. Tokens act as you.
        </p>
      </header>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 text-sm text-danger"
        >
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
          <Button
            variant="secondary"
            onClick={() => {
              setError("");
              void load();
            }}
          >
            Retry loading
          </Button>
        </div>
      )}
      {secret && (
        <section
          className="max-w-prose space-y-3 rounded-card border border-border bg-surface p-4"
          aria-label="New token"
        >
          <h2 className="text-md font-semibold">Copy your token now</h2>
          <p className="text-sm">
            This is the only time DocuHive will show it.
          </p>
          <Input
            aria-label="New API token"
            readOnly
            value={secret}
            autoComplete="off"
            className="font-mono"
          />
          <div className="flex gap-2">
            <Button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(secret);
                  setCopied(true);
                } catch {
                  setError(
                    "Copy the token from the field above. Clipboard access is unavailable.",
                  );
                }
              }}
            >
              {copied ? "Copied" : "Copy token"}
            </Button>
            <Button variant="secondary" onClick={() => setSecret("")}>
              Done
            </Button>
          </div>
        </section>
      )}
      <form
        onSubmit={create}
        className="max-w-prose space-y-4 rounded-card border border-border bg-surface p-4"
      >
        <h2 className="text-md font-semibold">Create token</h2>
        <label className="block space-y-1.5 text-sm font-medium">
          Name
          <Input
            required
            maxLength={100}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="For example, my local agent"
          />
        </label>
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-medium">Permissions</legend>
          {scopeOptions
            .filter((option) => admin || option.id !== "admin")
            .map((option) => (
              <label
                key={option.id}
                className="flex min-h-5 items-center gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  className={checkboxClass}
                  checked={scopes.includes(option.id)}
                  onChange={(event) =>
                    setScopes(
                      event.target.checked
                        ? [...scopes, option.id]
                        : scopes.filter((scope) => scope !== option.id),
                    )
                  }
                />
                {option.label}
              </label>
            ))}
        </fieldset>
        <label className="flex min-h-5 items-center gap-2 text-sm">
          <input
            type="checkbox"
            className={checkboxClass}
            checked={localConsumer}
            onChange={(event) => setLocalConsumer(event.target.checked)}
          />
          Local-only consumer
        </label>
        <p className="text-xs text-text-muted">
          Enable only for an app that keeps retrieved text on your network. This
          allows it to retrieve restricted documents you can access. Otherwise
          restricted chunks are excluded. The app must keep that promise.
        </p>
        <Button
          disabled={
            busy || scopes.length === 0 || name.trim().length === 0 || !!secret
          }
        >
          {busy ? "Saving…" : "Create token"}
        </Button>
      </form>
      <section className="space-y-3" aria-label="Your tokens">
        <h2 className="text-md font-semibold">Your tokens</h2>
        {loading && (
          <div
            role="status"
            className="h-24 animate-pulse rounded-card bg-surface-2 motion-reduce:animate-none"
            aria-label="Loading tokens"
          />
        )}
        {!loading && tokens.length === 0 && (
          <div className="space-y-2 rounded-card border border-border bg-surface p-4">
            <KeyRound className="size-5" aria-hidden="true" />
            <p className="text-sm">
              No tokens yet. Use the form above to connect an app or agent.
            </p>
          </div>
        )}
        {tokens.map((token) => (
          <article
            key={token.id}
            className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-border bg-surface p-4"
          >
            <div className="min-w-0">
              <h3 className="break-words font-medium">{token.name}</h3>
              <p className="break-words text-xs text-text-muted">
                {token.scopes.join(", ")} ·{" "}
                {token.local_consumer
                  ? "Local-only consumer"
                  : "Restricted chunks excluded"}
              </p>
              <p className="text-xs text-text-muted">
                {token.revoked_at
                  ? "Revoked"
                  : token.last_used_at
                    ? `Last used ${new Date(token.last_used_at).toLocaleString()}`
                    : "Never used"}
              </p>
            </div>
            {!token.revoked_at &&
              (revoking === token.id ? (
                <div className="space-y-2">
                  <p className="text-sm">
                    Revoke “{token.name}”? Its app will lose access.
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => setRevoking(null)}
                    >
                      Keep token
                    </Button>
                    <Button
                      variant="danger"
                      disabled={busy}
                      onClick={() => void revoke(token.id)}
                    >
                      Confirm revoke
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="secondary"
                  aria-label={`Revoke ${token.name}`}
                  disabled={busy}
                  onClick={() => setRevoking(token.id)}
                >
                  Revoke
                </Button>
              ))}
          </article>
        ))}
      </section>
      <a
        className="inline-block text-sm text-primary underline"
        href="https://github.com/d2k-klin/docuhive/blob/main/docs/setup/knowledge-bases.md"
        target="_blank"
        rel="noreferrer"
      >
        Knowledge bases and token privacy guide
      </a>
    </main>
  );
}
