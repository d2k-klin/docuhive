import { Suspense } from "react";
import { FileText } from "lucide-react";
import { LoginForm } from "@/components/core/login-form";

export default function Login() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-6">
      <FileText className="mb-4 size-5 text-primary" aria-hidden="true" />
      <h1 className="text-xl font-semibold">Sign in to DocuHive</h1>
      <p className="mb-6 mt-2 text-sm text-text-muted">
        Your documents, on your storage.
      </p>
      <section
        className="rounded-card border border-border bg-surface p-6"
        aria-label="Sign in"
      >
        <Suspense
          fallback={<p className="text-text-muted">Loading sign in…</p>}
        >
          <LoginForm />
        </Suspense>
      </section>
      <p className="mt-4 text-xs text-text-muted">
        An administrator creates your account. Contact them if you need access.
      </p>
    </main>
  );
}
