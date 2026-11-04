"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { TriangleAlert } from "lucide-react";
import type { components } from "@/lib/api/schema";

type Check = components["schemas"]["SetupCheck"];
export function OperationsStatus() {
  const [checks, setChecks] = useState<Check[]>([]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/system/setup-status", { cache: "no-store" });
        if (response.ok && active) setChecks(await response.json());
      } catch { /* The shell stays usable while connectivity returns. */ }
    };
    void load();
    const timer = setInterval(() => void load(), 60000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  const problems = checks.filter(check => ["error", "warn"].includes(check.status) && ["storage", "backup"].includes(check.area));
  if (!problems.length) return null;
  return <aside aria-label="Archive status" className="space-y-2 border-b border-border bg-surface-2 p-4 text-sm">
    {problems.map(check => <p key={check.id} className="flex items-start gap-2"><TriangleAlert aria-hidden="true" className="mt-1 size-4 shrink-0" /><span>{check.message} {check.action_href && <Link href={check.action_href} className="text-primary underline">{check.action_label}</Link>}</span></p>)}
  </aside>;
}
