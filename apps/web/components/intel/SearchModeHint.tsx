import Link from "next/link";
import { Info } from "lucide-react";

/** Slot: search page, under the query box. */
export function SearchModeHint({ semanticAvailable }: { semanticAvailable: boolean }) {
  if (semanticAvailable) return null;
  return (
    <p className="mt-2 flex items-center gap-1 text-xs text-text-muted">
      <Info aria-hidden="true" className="size-3" />
      Semantic search is off — configure an embedding model in{" "}
      <Link href="/settings/ai" className="text-primary hover:underline">Settings → AI</Link>.
    </p>
  );
}
