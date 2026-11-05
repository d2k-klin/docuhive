"use client";

import * as React from "react";
import { Mail, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  ApiError,
  ErrorBox,
  Field,
  Skeleton,
} from "@/components/intel/common";

export type Oauth = { google: boolean; microsoft: boolean };
type Known = {
  name: string;
  domains: string[];
  host?: string;
  oauth?: keyof Oauth;
  appPassword?: boolean;
  hint?: string;
  href?: string;
};

// Mail services whose IMAP server follows from the address. Outlook.com takes no IMAP passwords.
const KNOWN: Known[] = [
  {
    name: "Gmail",
    domains: ["gmail.com", "googlemail.com"],
    host: "imap.gmail.com",
    oauth: "google",
    appPassword: true,
    hint: "Gmail needs an app password, not your Google password. Turn on 2-Step Verification, then create one named DocuHive.",
    href: "https://myaccount.google.com/apppasswords",
  },
  {
    name: "Outlook",
    domains: [
      "outlook.com",
      "hotmail.com",
      "live.com",
      "msn.com",
      "outlook.de",
      "hotmail.de",
    ],
    oauth: "microsoft",
  },
  {
    name: "iCloud Mail",
    domains: ["icloud.com", "me.com", "mac.com"],
    host: "imap.mail.me.com",
    appPassword: true,
    hint: "iCloud needs an app-specific password from your Apple Account, not your Apple password.",
    href: "https://account.apple.com/account/manage",
  },
  {
    name: "Yahoo Mail",
    domains: ["yahoo.com", "yahoo.de"],
    host: "imap.mail.yahoo.com",
    appPassword: true,
    hint: "Yahoo needs an app password from your Yahoo account security settings.",
    href: "https://login.yahoo.com/account/security",
  },
  {
    name: "GMX",
    domains: ["gmx.de", "gmx.net", "gmx.at", "gmx.ch"],
    host: "imap.gmx.net",
    hint: "Use your GMX password. Turn on POP3/IMAP access in the GMX settings first.",
  },
  {
    name: "WEB.DE",
    domains: ["web.de"],
    host: "imap.web.de",
    hint: "Use your WEB.DE password. Turn on POP3/IMAP access in the WEB.DE settings first.",
  },
  {
    name: "Fastmail",
    domains: ["fastmail.com", "fastmail.fm"],
    host: "imap.fastmail.com",
    appPassword: true,
    hint: "Create an app password with mail access in Fastmail settings.",
    href: "https://app.fastmail.com/settings/security/devicekeys",
  },
  { name: "Posteo", domains: ["posteo.de", "posteo.net"], host: "posteo.de" },
  { name: "mailbox.org", domains: ["mailbox.org"], host: "imap.mailbox.org" },
  {
    name: "T-Online",
    domains: ["t-online.de", "magenta.de"],
    host: "secureimap.t-online.de",
    hint: "Use the separate password for e-mail programs from the T-Online e-mail settings.",
  },
];

function known(address: string): Known | null {
  const domain = address.split("@")[1]?.trim().toLowerCase() ?? "";
  return KNOWN.find((k) => k.domains.includes(domain)) ?? null;
}

export type Connection = {
  credentials_ready: boolean;
  sync_every_min: number;
  oauth_redirects: Record<keyof Oauth, string>;
};

type Provider = "google" | "microsoft" | "icloud" | "imap";
const PROVIDERS: { id: Provider; name: string; description: string }[] = [
  { id: "google", name: "Gmail", description: "Google & Google Workspace" },
  {
    id: "microsoft",
    name: "Outlook",
    description: "Microsoft 365, Hotmail & Live",
  },
  { id: "icloud", name: "iCloud Mail", description: "Apple email accounts" },
  {
    id: "imap",
    name: "Other email",
    description: "Yahoo, GMX, Fastmail & IMAP",
  },
];

function OAuthHelp({
  provider,
  redirect,
}: {
  provider: keyof Oauth;
  redirect?: string;
}) {
  const google = provider === "google";
  return (
    <details className="rounded border border-border bg-surface-2 p-3 text-sm">
      <summary className="cursor-pointer font-medium">
        Set up {google ? "Google" : "Microsoft"} sign-in on this server
      </summary>
      <div className="mt-3 space-y-3 text-text-muted">
        <p>
          A server administrator does this once. After that, everyone can
          connect using their usual sign-in.
        </p>
        <ol className="list-decimal space-y-2 pl-5">
          <li>
            <a
              className="text-primary underline"
              target="_blank"
              rel="noreferrer"
              href={
                google
                  ? "https://console.cloud.google.com/apis/credentials"
                  : "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
              }
            >
              Open{" "}
              {google ? "Google Cloud Console" : "Microsoft app registrations"}
            </a>{" "}
            and register a web application.{" "}
            {google
              ? "Enable the Gmail API and add your account as a test user on the consent screen."
              : "Allow the account types you want to connect, including personal accounts if needed."}
          </li>
          <li>
            Add this redirect address
            {redirect ? (
              <>
                :{" "}
                <code className="mt-1 block break-all rounded bg-surface p-2 text-xs text-text">
                  {redirect}
                </code>
              </>
            ) : (
              " from your server's public URL."
            )}
          </li>
          <li>
            {google
              ? "Request gmail.readonly access. Publish the consent screen for ongoing use; test access expires after seven days."
              : "Add delegated Mail.Read, User.Read and offline_access permissions, then create a client secret."}
          </li>
          <li>
            Add the client ID and secret to the server environment, then restart
            DocuHive:
            <code className="mt-1 block break-all rounded bg-surface p-2 text-xs text-text">
              DOCUHIVE_MAIL_{google ? "GOOGLE" : "MS"}_CLIENT_ID
              <br />
              DOCUHIVE_MAIL_{google ? "GOOGLE" : "MS"}_CLIENT_SECRET
            </code>
          </li>
        </ol>
        <Button
          type="button"
          variant="secondary"
          onClick={() => window.location.reload()}
        >
          Check setup again
        </Button>
      </div>
    </details>
  );
}

export function ConnectMailbox({
  initial,
  oauth,
  connection,
  onDone,
}: {
  initial: string;
  oauth: Oauth | undefined;
  connection?: Connection;
  onDone: (account: { id: number; address: string }) => void;
}) {
  const [provider, setProvider] = React.useState<Provider | null>(
    initial === "gmail"
      ? "google"
      : initial === "outlook" || initial === "graph"
        ? "microsoft"
        : initial === "imap" || initial === "icloud"
          ? initial
          : null,
  );
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [usePassword, setUsePassword] = React.useState(false);
  const [custom, setCustom] = React.useState({
    host: "",
    port: "993",
    username: "",
    folders: "INBOX",
  });
  const [error, setError] = React.useState<ApiError | null>(null);
  const [busy, setBusy] = React.useState(false);
  const service =
    provider === "google"
      ? KNOWN[0]
      : provider === "icloud"
        ? KNOWN[2]
        : known(email);
  const host = custom.host.trim() || service?.host || "";
  const signIn =
    provider === "google" || provider === "microsoft" ? provider : null;
  const passwordForm =
    provider &&
    provider !== "microsoft" &&
    (!signIn || !oauth?.[signIn] || usePassword);
  const ready = connection?.credentials_ready !== false;

  return (
    <div className="space-y-5">
      <ol
        aria-label="Connection progress"
        className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-text-muted"
      >
        <li
          aria-current={!provider ? "step" : undefined}
          className={!provider ? "font-medium text-text" : ""}
        >
          1. Choose provider
        </li>
        <li
          aria-current={provider ? "step" : undefined}
          className={provider ? "font-medium text-text" : ""}
        >
          2. Connect securely
        </li>
        <li>3. Import attachments</li>
      </ol>
      {!provider ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setProvider(p.id)}
              className="flex min-h-control-lg items-center gap-3 rounded-card border border-border bg-surface p-4 text-left transition-colors hover:border-primary hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            >
              <Mail
                aria-hidden="true"
                className="size-5 shrink-0 text-primary"
              />
              <span>
                <span className="block font-medium">{p.name}</span>
                <span className="block text-xs text-text-muted">
                  {p.description}
                </span>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="max-w-2xl space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">
              Connect {PROVIDERS.find((p) => p.id === provider)?.name}
            </h3>
            <Button
              size="sm"
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setProvider(null);
                setPassword("");
                setCustom({
                  host: "",
                  port: "993",
                  username: "",
                  folders: "INBOX",
                });
                setUsePassword(false);
                setError(null);
              }}
            >
              Change provider
            </Button>
          </div>
          {!ready && (
            <div
              role="alert"
              className="space-y-2 rounded border border-warning bg-surface-2 p-3 text-sm"
            >
              <p className="font-medium">
                Mail credential storage needs setting up first.
              </p>
              <p>
                An administrator must run <code>docuhive mail gen-key</code>,
                save the result as{" "}
                <code className="break-all">DOCUHIVE_MAIL_TOKEN_KEY</code> in
                the server environment, then restart DocuHive. This keeps
                mailbox passwords and sign-in tokens encrypted.
              </p>
              <Button
                type="button"
                variant="secondary"
                onClick={() => window.location.reload()}
              >
                Check setup again
              </Button>
            </div>
          )}
          {signIn && oauth === undefined ? (
            <Skeleton rows={2} />
          ) : signIn && oauth?.[signIn] && !usePassword ? (
            <div className="space-y-3">
              <p className="text-sm text-text-muted">
                Sign in with {signIn === "google" ? "Google" : "Microsoft"} and
                allow DocuHive to read your email. Your password stays with your
                provider.
              </p>
              {ready && (
                <Button asChild>
                  <a href={`/api/sources/oauth/${signIn}/start`}>
                    Continue with {signIn === "google" ? "Google" : "Microsoft"}
                  </a>
                </Button>
              )}
              {signIn === "google" && (
                <div>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setUsePassword(true)}
                  >
                    Use an app password instead
                  </Button>
                </div>
              )}
            </div>
          ) : signIn && !oauth?.[signIn] ? (
            <div className="space-y-3">
              <p className="text-sm text-text-muted">
                {signIn === "google"
                  ? "Google sign-in isn't enabled on this server. You can connect now with a Google app password."
                  : "Outlook requires Microsoft sign-in. An administrator needs to enable it on this server before you can connect."}
              </p>
              <OAuthHelp
                provider={signIn}
                redirect={connection?.oauth_redirects[signIn]}
              />
            </div>
          ) : null}
          {passwordForm && (
            <form
              className="space-y-4"
              onSubmit={async (e) => {
                e.preventDefault();
                if (busy || !ready || !host) return;
                setBusy(true);
                setError(null);
                try {
                  const account = await api<{ id: number; address: string }>(
                    "/api/sources/accounts",
                    {
                      method: "POST",
                      json: {
                        provider: "imap",
                        host,
                        port: Number(custom.port),
                        username: custom.username.trim() || email.trim(),
                        password,
                        address: email.trim(),
                        folders: custom.folders
                          .split(",")
                          .map((x) => x.trim())
                          .filter(Boolean),
                      },
                    },
                  );
                  setPassword("");
                  onDone(account);
                } catch (err) {
                  setError(err as ApiError);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <div className="grid gap-4 lg:grid-cols-2">
                <Field label="Email address">
                  <Input
                    required
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </Field>
                <Field
                  label={service?.appPassword ? "App password" : "Password"}
                  help="Stored encrypted on your server."
                >
                  <Input
                    required
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </Field>
              </div>
              {service?.hint && (
                <p className="text-sm text-text-muted">
                  {service.hint}{" "}
                  {service.href && (
                    <a
                      href={service.href}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary underline"
                    >
                      Create an app password
                    </a>
                  )}
                </p>
              )}
              {service?.oauth === "microsoft" && provider === "imap" && (
                <p role="alert" className="text-sm text-warning">
                  Microsoft mailboxes require sign-in. Choose Outlook above.
                </p>
              )}
              <details open={provider === "imap" && !service?.host}>
                <summary className="cursor-pointer text-sm font-medium">
                  Server settings
                  {host ? ` · ${host}` : " · required for your provider"}
                </summary>
                <div className="mt-3 grid gap-4 lg:grid-cols-2">
                  <Field label="Mail server">
                    <Input
                      required={!service?.host}
                      placeholder={service?.host || "imap.example.org"}
                      value={custom.host}
                      onChange={(e) =>
                        setCustom({ ...custom, host: e.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="Port"
                    help="Encrypted connection (TLS). Usually 993."
                  >
                    <Input
                      required
                      type="number"
                      min={1}
                      max={65535}
                      value={custom.port}
                      onChange={(e) =>
                        setCustom({ ...custom, port: e.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="Username"
                    help="Leave blank to use your email address."
                  >
                    <Input
                      autoComplete="username"
                      placeholder={email || "you@example.com"}
                      value={custom.username}
                      onChange={(e) =>
                        setCustom({ ...custom, username: e.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="Folders to watch"
                    help="Comma-separated. Use a dedicated folder to import only mail you put there."
                  >
                    <Input
                      required
                      value={custom.folders}
                      onChange={(e) =>
                        setCustom({ ...custom, folders: e.target.value })
                      }
                    />
                  </Field>
                </div>
              </details>
              {error && <ErrorBox error={error} />}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-text-muted">
                  We test your login before saving the connection.
                </p>
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    !ready ||
                    !host ||
                    (provider === "imap" && service?.oauth === "microsoft")
                  }
                >
                  {busy ? (
                    <>
                      <RefreshCw
                        className="motion-safe:animate-spin"
                        aria-hidden="true"
                      />{" "}
                      Checking connection…
                    </>
                  ) : (
                    "Connect mailbox"
                  )}
                </Button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
