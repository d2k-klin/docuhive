"use client";

import { useState } from "react";
import { Download, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { errorMessage } from "@/lib/i18n/errors";
import { Button } from "@/components/ui/button";

type ExportRequest = components["schemas"]["ExportRequest"];
const api = browserClient();

/** Downloads a ZIP of the archive PDFs plus a CSV of their details. */
export function ExportButton({
  source,
  label,
}: {
  source: ExportRequest;
  label: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    setBusy(true);
    setError("");
    try {
      const response = await api.POST("/api/export", {
        body: source,
        parseAs: "blob",
      });
      if (!response.response.ok || !response.data) {
        const body = (await response.response
          .clone()
          .json()
          .catch(() => null)) as { error?: { code?: string } } | null;
        setError(errorMessage(body?.error?.code));
        return;
      }
      const name =
        /filename="([^"]+)"/.exec(
          response.response.headers.get("content-disposition") || "",
        )?.[1] || "docuhive-export.zip";
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("The export could not be created. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="secondary"
        disabled={busy}
        aria-label={label}
        onClick={() => void run()}
      >
        <Download aria-hidden="true" />
        {busy ? "Preparing export…" : "Export"}
      </Button>
      {error && (
        <p role="alert" className="flex items-center gap-2 text-sm text-danger">
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  );
}
