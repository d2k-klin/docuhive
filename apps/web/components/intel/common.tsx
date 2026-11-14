"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Cloud,
  HardDrive,
  Info,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/** Same-origin call through the BFF proxy; errors carry the API's plain-language message. */
export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...rest } = init;
  const res = await fetch(path, {
    ...rest,
    headers: {
      "X-DocuHive-CSRF": "1",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...rest.headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = body.error ?? body.detail ?? {};
    throw new ApiError(
      err.code ?? `http_${res.status}`,
      err.message ?? "Something went wrong. Try again in a moment.",
      res.status,
    );
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** Load once (and on `reload()`), with loading and error state. */
export function useApi<T>(path: string | null) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [tick, setTick] = React.useState(0);
  const key = `${path}#${tick}`;
  const [loadedKey, setLoadedKey] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!path) return;
    let live = true;
    api<T>(path)
      .then((d) => live && (setData(d), setError(null)))
      .catch((e: ApiError) => live && setError(e))
      .finally(() => live && setLoadedKey(key));
    return () => {
      live = false;
    };
  }, [path, key]);
  const reload = React.useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading: Boolean(path) && loadedKey !== key, reload, setData };
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold">{title}</h1>
        {description && (
          <p className="text-sm text-text-muted">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Page({
  children,
  narrow,
}: {
  children: React.ReactNode;
  narrow?: boolean;
}) {
  return (
    <main
      className={cn("mx-auto p-4 md:p-6", narrow ? "max-w-3xl" : "max-w-7xl")}
    >
      {children}
    </main>
  );
}

export function Card({
  title,
  children,
  className,
  actions,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-card border border-border bg-surface p-4",
        className,
      )}
    >
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-md font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const tones: Record<string, { cls: string; icon: LucideIcon }> = {
  ok: { cls: "text-success", icon: CheckCircle2 },
  warn: { cls: "text-warning", icon: AlertTriangle },
  error: { cls: "text-danger", icon: XCircle },
  info: { cls: "text-info", icon: Info },
  muted: { cls: "text-text-muted", icon: CircleDashed },
};

/** Status always pairs colour + icon + text. */
export function Badge({
  tone = "muted",
  children,
  icon,
}: {
  tone?: keyof typeof tones;
  children: React.ReactNode;
  icon?: LucideIcon;
}) {
  const t = tones[tone];
  const Icon = icon ?? t.icon;
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-md border border-border bg-surface-2 px-2 text-xs font-medium",
        t.cls,
      )}
    >
      <Icon aria-hidden="true" className="size-3" />
      <span className="text-text">{children}</span>
    </span>
  );
}

export function LocalBadge({ local }: { local: boolean }) {
  return local ? (
    <Badge tone="ok" icon={HardDrive}>
      Local
    </Badge>
  ) : (
    <Badge tone="info" icon={Cloud}>
      Cloud
    </Badge>
  );
}

export function Empty({
  icon: Icon,
  text,
  action,
}: {
  icon: LucideIcon;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-card border border-dashed border-border-strong p-8 text-center">
      <Icon aria-hidden="true" className="size-5 text-text-muted" />
      <p className="max-w-prose">{text}</p>
      {action}
    </div>
  );
}

export function ErrorBox({
  error,
  onRetry,
}: {
  error: ApiError | Error;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger bg-surface p-4"
    >
      <p className="flex items-center gap-2">
        <XCircle aria-hidden="true" className="size-4 text-danger" />
        {error.message}
      </p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Skeleton({
  rows = 3,
  className,
}: {
  rows?: number;
  className?: string;
}) {
  return (
    <div role="status" aria-busy="true" aria-label="Loading" className={cn("space-y-2", className)}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-10 animate-pulse rounded bg-surface-2" />
      ))}
    </div>
  );
}

export function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-medium">{label}</span>
      {children}
      {help && <span className="block text-xs text-text-muted">{help}</span>}
    </label>
  );
}

export function Meter({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <span className="inline-flex items-center gap-2" title={`${label}: ${pct}%`}>
      <span
        role="meter"
        aria-label={label}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-1.5 w-16 overflow-hidden rounded bg-surface-2"
      >
        <span
          className={cn(
            "block h-full",
            pct >= 80 ? "bg-success" : pct >= 50 ? "bg-warning" : "bg-danger",
          )}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="tabular text-xs text-text-muted">{pct}%</span>
    </span>
  );
}

export function formatDate(value?: string | null): string {
  if (!value) return "–";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatMoney(value: string | number, currency?: string | null) {
  const n = Number(value);
  if (!currency || Number.isNaN(n)) return String(value);
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(n);
}

/** Human labels for field names: "document_type" -> "Document type", "facts.amount_total" -> "Amount total". */
export function fieldLabel(field: string): string {
  const name = field.replace(/^facts\./, "").replace(/_/g, " ");
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function daysLeft(n: number): string {
  if (n === 0) return "today";
  if (n < 0) return `${-n} days ago`;
  return n === 1 ? "tomorrow" : `in ${n} days`;
}
