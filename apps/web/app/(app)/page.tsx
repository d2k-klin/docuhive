import Link from "next/link";
import { FileText, Search, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SetupChecklist } from "@/components/core/setup-checklist";

export default function Home() {
  return (
    <main className="mx-auto max-w-7xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <FileText aria-hidden="true" className="size-5 text-primary" />
          <div>
            <h1 className="text-xl font-semibold">DocuHive</h1>
            <p className="text-sm text-text-muted">
              Your documents, on your storage.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" asChild>
            <Link href="/search">
              <Search aria-hidden="true" />
              Search
            </Link>
          </Button>
          <Button asChild>
            <Link href="/upload">
              <Upload aria-hidden="true" />
              Upload
            </Link>
          </Button>
        </div>
      </header>
      <SetupChecklist />
    </main>
  );
}
