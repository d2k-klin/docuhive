"use client";

import { useState } from "react";
import { TriangleAlert, Users as UsersIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox as checkboxClass, control } from "@/lib/ui/control";

type Role = "admin" | "member" | "bookkeeper";
type Person = { id: number; username: string; role: Role; disabled: boolean };
type Category = { id: string; label: string };

const roles: { id: Role; label: string; help: string }[] = [
  {
    id: "member",
    label: "Member",
    help: "Own documents and the household's shared ones",
  },
  {
    id: "bookkeeper",
    label: "Bookkeeper",
    help: "Like a member, plus the categories chosen below",
  },
  {
    id: "admin",
    label: "Administrator",
    help: "Also settings, users and plugins",
  },
];

async function call(path: string, method = "GET", body?: unknown) {
  const res = await fetch(path, {
    method,
    headers: { "X-DocuHive-CSRF": "1", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.error?.message ?? data?.detail;
    throw new Error(
      typeof detail === "string" ? detail : "That did not work. Try again.",
    );
  }
  return data;
}

/** Administrators: who may sign in, and with which role. Visibility never grows by role
 * except for the bookkeeper categories an administrator chooses here. */
export function Users({
  initial,
  categories,
  bookkeeper,
  viewerId,
}: {
  initial: Person[];
  categories: Category[];
  bookkeeper: string[];
  viewerId: number;
}) {
  const [people, setPeople] = useState(initial);
  const [shared, setShared] = useState<string[]>(bookkeeper);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [enabling, setEnabling] = useState<number | null>(null);
  const [draft, setDraft] = useState({
    username: "",
    password: "",
    role: "member" as Role,
  });

  async function run(work: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      const list = await call("/api/users?limit=200");
      setPeople(list.items);
      setNotice(done);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header>
        <h1 className="text-xl font-semibold">Users</h1>
        <p className="text-sm text-text-muted">
          Who may sign in. A role never shows anyone another person&apos;s
          private documents, except the categories you give bookkeepers below.
        </p>
      </header>
      {error && (
        <p role="alert" className="flex items-center gap-2 text-sm text-danger">
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm text-success">
          {notice}
        </p>
      )}
      <ul className="divide-y divide-border rounded-card border border-border bg-surface">
        {people.map((p) => (
          <li
            key={p.id}
            className="flex flex-wrap items-center justify-between gap-3 p-4"
          >
            <div>
              <p className="font-medium">
                {p.username}
                {p.id === viewerId ? " (you)" : ""}
              </p>
              <p className="text-sm text-text-muted">
                {p.disabled
                  ? "Cannot sign in"
                  : roles.find((r) => r.id === p.role)?.help}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="sr-only" htmlFor={`role-${p.id}`}>
                Role of {p.username}
              </label>
              <select
                id={`role-${p.id}`}
                className={control}
                value={p.role}
                disabled={busy || p.disabled}
                onChange={(e) =>
                  void run(
                    () =>
                      call(`/api/users/${p.id}`, "PATCH", {
                        role: e.target.value,
                      }),
                    `${p.username} is now ${roles.find((r) => r.id === e.target.value)?.label}.`,
                  )
                }
              >
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
              </select>
              {!p.disabled && p.id !== viewerId && (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Stop ${p.username} from signing in? Their documents stay.`,
                      )
                    )
                      void run(
                        () =>
                          call(`/api/users/${p.id}`, "PATCH", {
                            disabled: true,
                          }),
                        `${p.username} can no longer sign in.`,
                      );
                  }}
                >
                  Disable
                </Button>
              )}
              {p.disabled && enabling !== p.id && (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={busy}
                  onClick={() => setEnabling(p.id)}
                >
                  Enable
                </Button>
              )}
              {enabling === p.id && (
                <form
                  className="flex items-center gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const password = new FormData(e.currentTarget).get(
                      "password",
                    );
                    void run(
                      () =>
                        call(`/api/users/${p.id}`, "PATCH", {
                          disabled: false,
                          password,
                        }),
                      `${p.username} can sign in again with the new password.`,
                    ).then(() => setEnabling(null));
                  }}
                >
                  <label className="sr-only" htmlFor={`pw-${p.id}`}>
                    New password for {p.username}
                  </label>
                  <Input
                    id={`pw-${p.id}`}
                    name="password"
                    type="password"
                    required
                    minLength={12}
                    autoComplete="new-password"
                    placeholder="New password"
                  />
                  <Button type="submit" size="sm" disabled={busy}>
                    Enable
                  </Button>
                </form>
              )}
            </div>
          </li>
        ))}
      </ul>
      <form
        className="space-y-4 rounded-card border border-border bg-surface p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            () => call("/api/users", "POST", draft),
            `${draft.username} can sign in now.`,
          ).then(() =>
            setDraft({ username: "", password: "", role: "member" }),
          );
        }}
      >
        <h2 className="text-md font-semibold">Add a person</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="block space-y-1.5 text-sm font-medium">
            User name
            <Input
              required
              maxLength={100}
              autoComplete="off"
              value={draft.username}
              onChange={(e) => setDraft({ ...draft, username: e.target.value })}
            />
          </label>
          <label className="block space-y-1.5 text-sm font-medium">
            First password (at least 12 characters)
            <Input
              required
              type="password"
              minLength={12}
              autoComplete="new-password"
              value={draft.password}
              onChange={(e) => setDraft({ ...draft, password: e.target.value })}
            />
          </label>
          <label className="block space-y-1.5 text-sm font-medium">
            Role
            <select
              className={control}
              value={draft.role}
              onChange={(e) =>
                setDraft({ ...draft, role: e.target.value as Role })
              }
            >
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <Button type="submit" disabled={busy}>
          Add
        </Button>
      </form>
      <form
        className="space-y-3 rounded-card border border-border bg-surface p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            () =>
              call("/api/users/roles/bookkeeper", "PUT", {
                categories: shared,
              }),
            "Saved: bookkeepers see these categories.",
          );
        }}
      >
        <h2 className="text-md font-semibold">What bookkeepers may see</h2>
        <p className="text-sm text-text-muted">
          Besides their own and shared documents, people with the bookkeeper
          role see every document in these categories (and their subcategories).
          None chosen: they see what a member sees.
        </p>
        <fieldset className="flex max-h-56 flex-wrap gap-x-6 gap-y-2 overflow-auto">
          <legend className="sr-only">Categories</legend>
          {categories.map((c) => (
            <label
              key={c.id}
              className="flex min-h-5 items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                className={checkboxClass}
                checked={shared.includes(c.id)}
                onChange={(e) =>
                  setShared(
                    e.target.checked
                      ? [...shared, c.id]
                      : shared.filter((x) => x !== c.id),
                  )
                }
              />
              {c.label}
            </label>
          ))}
        </fieldset>
        <Button type="submit" variant="secondary" disabled={busy}>
          <UsersIcon aria-hidden="true" />
          Save
        </Button>
      </form>
    </main>
  );
}
