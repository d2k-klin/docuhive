"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  ApiError,
  Card,
  Field,
  Page,
  PageHeader,
} from "@/components/intel/common";

export function AccountPage({
  username,
  role,
}: {
  username: string;
  role: string;
}) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const mismatch = repeat.length > 0 && repeat !== next;
  async function change() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api("/api/auth/password", {
        method: "POST",
        json: { current_password: current, new_password: next },
      });
      setMessage("Password changed. Other devices are signed out.");
      setCurrent("");
      setNext("");
      setRepeat("");
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page narrow>
      <PageHeader
        title="Settings"
        description={`Signed in as ${username} (${role}).`}
      />
      <div className="space-y-6">
        <Card title="Password">
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void change();
            }}
          >
            <Field label="Current password">
              <Input
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </Field>
            <Field label="New password" help="At least 12 characters.">
              <Input
                type="password"
                autoComplete="new-password"
                minLength={12}
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </Field>
            <Field label="Repeat new password">
              <Input
                type="password"
                autoComplete="new-password"
                aria-invalid={mismatch}
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
              />
            </Field>
            {mismatch && (
              <p role="alert" className="text-sm text-danger">
                The passwords do not match.
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            {message && (
              <p role="status" className="text-sm text-success">
                {message}
              </p>
            )}
            <div className="flex justify-end">
              <Button
                type="submit"
                disabled={busy || !current || next.length < 12 || mismatch}
              >
                {busy ? "Changing…" : "Change password"}
              </Button>
            </div>
          </form>
        </Card>
        <Card title="More settings">
          <ul className="space-y-2 text-sm">
            <li>
              <Link
                className="text-primary hover:underline"
                href="/settings/tokens"
              >
                API tokens
              </Link>{" "}
              for scripts, iOS Shortcuts and other agents
            </li>
            <li>
              <Link
                className="text-primary hover:underline"
                href="/settings/notifications"
              >
                Notifications
              </Link>{" "}
              and reminders
            </li>
            <li>
              <Link className="text-primary hover:underline" href="/trash">
                Trash
              </Link>{" "}
              to restore deleted documents
            </li>
          </ul>
        </Card>
      </div>
    </Page>
  );
}
