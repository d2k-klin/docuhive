"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { safeNext } from "@/lib/auth";
import { errorMessage } from "@/lib/i18n/errors";
import { en } from "@/lib/i18n/en";

export function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json", "X-DocuHive-CSRF": "1" },
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setError(
          response.status === 401
            ? "Username or password is incorrect."
            : errorMessage(body.error?.code),
        );
        return;
      }
      router.replace(safeNext(search.get("next")));
      router.refresh();
    } catch {
      setError(errorMessage("api_unavailable"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="username" className="mb-1.5 block text-sm font-medium">
          {en.username}
        </label>
        <Input
          id="username"
          name="username"
          autoComplete="username"
          required
          maxLength={100}
        />
      </div>
      <div>
        <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
          {en.password}
        </label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={1024}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <Button type="submit" disabled={busy} className="w-full">
        {busy ? "Signing in…" : en.signIn}
      </Button>
    </form>
  );
}
