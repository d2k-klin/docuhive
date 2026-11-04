import { FileText } from "lucide-react";

export default function Home() {
  return (
    <main className="mx-auto max-w-7xl p-4 md:p-6">
      <header className="mb-6 flex items-center gap-3">
        <FileText aria-hidden="true" className="size-5 text-primary" />
        <div>
          <h1 className="text-xl font-semibold">DocuHive</h1>
          <p className="text-sm text-text-muted">
            Your documents, on your storage.
          </p>
        </div>
      </header>
      <section
        className="rounded-card border border-border bg-surface p-5"
        aria-labelledby="setup-title"
      >
        <h2 id="setup-title" className="text-md font-semibold">
          Start with your archive
        </h2>
        <p className="mt-2 max-w-prose text-text-muted">
          Your archive is being set up. Connect storage before adding documents.
        </p>
        <p className="mt-4 text-sm text-text-muted">
          Storage setup will guide you through the next step when it is
          available.
        </p>
      </section>
    </main>
  );
}
