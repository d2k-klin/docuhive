"use client";

import Link from "next/link";
import {
  CheckCircle2,
  CircleDashed,
  ListChecks,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import type { components } from "@/lib/api/schema";
import { Card, ErrorBox, Skeleton, useApi } from "@/components/intel/common";

type Check = components["schemas"]["SetupCheck"];

const ICONS = {
  ok: { icon: CheckCircle2, cls: "text-success", label: "Done" },
  todo: { icon: CircleDashed, cls: "text-text-muted", label: "To do" },
  warn: { icon: TriangleAlert, cls: "text-warning", label: "Check" },
  error: { icon: XCircle, cls: "text-danger", label: "Problem" },
  optional: { icon: CircleDashed, cls: "text-text-subtle", label: "Optional" },
};

/** Every area's setup checks in one list; the user always sees the next step. */
export function SetupChecklist() {
  const results = [
    useApi<Check[]>("/api/system/setup-status"),
    useApi<Check[]>("/api/ai/setup-status"),
    useApi<Check[]>("/api/sources/setup-status"),
    useApi<Check[]>("/api/notifications/setup-status"),
  ];
  const checks = results.flatMap((r) => r.data || []);
  const failed = results.find((r) => r.error && r.error.status !== 404);
  const loading = results.some((r) => r.loading);
  const required = checks.filter((c) => c.required && c.status !== "ok");
  return (
    <Card title="Set up your archive">
      {failed?.error ? (
        <ErrorBox error={failed.error} onRetry={failed.reload} />
      ) : loading && !checks.length ? (
        <Skeleton rows={4} />
      ) : (
        <div className="space-y-3">
          <p className="flex items-center gap-2 text-sm text-text-muted">
            <ListChecks aria-hidden="true" className="size-4" />
            {required.length
              ? `${required.length} required ${required.length === 1 ? "step" : "steps"} left.`
              : "Everything required is done. Your archive runs on its own."}
          </p>
          <ul className="divide-y divide-border">
            {checks.map((check) => {
              const tone = ICONS[check.status];
              const Icon = tone.icon;
              return (
                <li
                  key={check.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-2"
                >
                  <div className="flex min-w-0 items-start gap-2">
                    <Icon
                      aria-hidden="true"
                      className={`mt-0.5 size-4 shrink-0 ${tone.cls}`}
                    />
                    <div className="min-w-0">
                      <p className="font-medium">
                        {check.title}
                        <span className="sr-only"> ({tone.label})</span>
                      </p>
                      <p className="text-sm text-text-muted">{check.message}</p>
                    </div>
                  </div>
                  {check.status !== "ok" && check.action_href && (
                    <Link
                      href={check.action_href}
                      className="text-sm text-primary hover:underline"
                    >
                      {check.action_label || "Open"}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}
