"use client";

import { useState } from "react";
import { IdCard, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { checkbox as checkboxClass, control } from "@/lib/ui/control";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Profile = components["schemas"]["ProfileOut"];
type Draft = components["schemas"]["ProfileIn"];
type Smtp = components["schemas"]["SmtpIn"];
const api = browserClient();
const kinds: { id: Draft["kind"]; label: string }[] = [
  { id: "business", label: "Business or self-employed" },
  { id: "person", label: "Person" },
  { id: "household", label: "Household" },
];
const empty: Draft = {
  kind: "business",
  name: "",
  shared: false,
  address: { street: "", postcode: "", city: "", country: "DE" },
  bank: { holder: "", iban: "", bic: "", name: "" },
  smtp: null,
};
const names: Record<string, string> = {
  iban: "IBAN",
  vat_id: "VAT id",
  email: "Email",
  from_address: "Sender address",
  host: "Mail server",
  name: "Name",
};

/** "body.bank.iban" -> "IBAN": which field the server refused, in words. */
function refused(body: unknown): string {
  const fields =
    (body as { error?: { details?: { fields?: string[] } } })?.error?.details
      ?.fields || [];
  const labels = fields.map((f) => names[f.split(".").pop() || ""] || f);
  return labels.length
    ? `Check ${[...new Set(labels)].join(", ")}.`
    : "The identity could not be saved. Try again.";
}

export function Identities({
  initial,
  viewerId,
}: {
  initial: Profile[] | null;
  viewerId: number;
}) {
  const [items, setItems] = useState<Profile[]>(initial || []);
  const [error, setError] = useState(
    initial ? "" : "Identities could not be loaded. Try again.",
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  async function load() {
    setError("");
    const response = await api.GET("/api/profiles").catch(() => null);
    if (!response?.data) {
      setError("Identities could not be loaded. Try again.");
      return;
    }
    setItems(response.data);
  }
  function start(profile?: Profile) {
    setEditing(profile?.id ?? null);
    setDraft(
      profile
        ? {
            ...profile,
            smtp: profile.smtp ? { ...profile.smtp, password: "" } : null,
          }
        : empty,
    );
    setError("");
  }
  const set = (patch: Partial<Draft>) =>
    setDraft({ ...(draft as Draft), ...patch });
  const setAddress = (key: string, value: string) =>
    set({ address: { ...empty.address!, ...draft?.address, [key]: value } });
  const setBank = (key: string, value: string) =>
    set({ bank: { ...empty.bank!, ...draft?.bank, [key]: value } });
  const setSmtp = (patch: Partial<Smtp>) =>
    set({
      smtp: {
        host: "",
        port: 587,
        username: "",
        from_address: "",
        ...(draft?.smtp || {}),
        ...patch,
      },
    });

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const body = { ...draft, email: draft.email || null };
      const response =
        editing === null
          ? await api.POST("/api/profiles", { body })
          : await api.PUT("/api/profiles/{profile_id}", {
              params: { path: { profile_id: editing } },
              body,
            });
      if (!response.data) {
        setError(refused(response.error));
        return;
      }
      setDraft(null);
      setEditing(null);
      window.scrollTo({ top: 0 });
      await load();
    } catch {
      setError("The identity could not be saved. Try again.");
    } finally {
      setBusy(false);
    }
  }
  async function testMail(id: number) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await api.POST("/api/profiles/{profile_id}/test-mail", {
        params: { path: { profile_id: id } },
      });
      if (!response.response.ok) {
        const body = response.error as { error?: { message?: string } };
        setError(body?.error?.message || "The test mail could not be sent.");
        return;
      }
      setNotice((response.data as { message?: string })?.message || "Sent.");
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: number) {
    setBusy(true);
    try {
      const response = await api.DELETE("/api/profiles/{profile_id}", {
        params: { path: { profile_id: id } },
      });
      if (!response.response.ok) throw new Error();
      await load();
    } catch {
      setError("The identity could not be removed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const text = (
    label: string,
    value: string | null | undefined,
    onChange: (value: string) => void,
    props: React.ComponentProps<typeof Input> = {},
  ) => (
    <label className="block space-y-1.5 text-sm font-medium">
      {label}
      <Input
        value={value || ""}
        onChange={(event) => onChange(event.target.value)}
        {...props}
      />
    </label>
  );

  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Identities</h1>
          <p className="text-sm text-text-muted">
            Who you are when DocuHive writes or sends something: on invoices,
            letters and mail.
          </p>
        </div>
        <Button disabled={busy} onClick={() => start()}>
          Add identity
        </Button>
      </header>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 text-sm text-danger"
        >
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
        </div>
      )}
      {notice && (
        <p role="status" className="text-sm text-success">
          {notice}
        </p>
      )}
      {!items.length && !draft && !error && (
        <div className="space-y-2 rounded-card border border-border bg-surface p-4">
          <IdCard className="size-5" aria-hidden="true" />
          <h2 className="text-md font-semibold">No identities yet</h2>
          <p className="text-sm text-text-muted">
            Add your business or your household once; plugins such as tax and
            invoicing use it.
          </p>
        </div>
      )}
      {!draft && items.length > 0 && (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface">
          {items.map((p) => (
            <li
              key={p.id}
              className="flex flex-wrap items-center justify-between gap-3 p-4"
            >
              <div>
                <p className="font-medium">{p.name}</p>
                <p className="text-sm text-text-muted">
                  {[
                    kinds.find((k) => k.id === p.kind)?.label,
                    p.address?.city,
                    p.shared ? "Shared with the household" : "Only you",
                    p.smtp ? "Can send mail" : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              {p.owner_id === viewerId && (
                <div className="flex gap-2">
                  {p.smtp && (
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busy}
                      onClick={() => void testMail(p.id)}
                    >
                      Send test mail
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => start(p)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm(`Remove “${p.name}”?`))
                        void remove(p.id);
                    }}
                  >
                    Remove
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {draft && (
        <form
          className="space-y-6 rounded-card border border-border bg-surface p-4"
          onSubmit={save}
        >
          <h2 className="text-md font-semibold">
            {editing === null ? "Add identity" : "Edit identity"}
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block space-y-1.5 text-sm font-medium">
              Kind
              <select
                className={control}
                value={draft.kind}
                onChange={(event) =>
                  set({ kind: event.target.value as Draft["kind"] })
                }
              >
                {kinds.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.label}
                  </option>
                ))}
              </select>
            </label>
            {text("Name", draft.name, (name) => set({ name }), {
              required: true,
              maxLength: 200,
            })}
            {draft.kind === "business" &&
              text("Legal form", draft.legal_form, (legal_form) =>
                set({ legal_form }),
              )}
            {text("Email", draft.email, (email) => set({ email }), {
              type: "email",
            })}
            {text("Phone", draft.phone, (phone) => set({ phone }))}
            {text("Website", draft.website, (website) => set({ website }))}
          </div>
          <fieldset className="grid gap-4 md:grid-cols-2">
            <legend className="mb-2 text-sm font-semibold">Address</legend>
            {text("Street and number", draft.address?.street, (v) =>
              setAddress("street", v),
            )}
            {text("Postcode", draft.address?.postcode, (v) =>
              setAddress("postcode", v),
            )}
            {text("City", draft.address?.city, (v) => setAddress("city", v))}
            {text("Country", draft.address?.country, (v) =>
              setAddress("country", v),
            )}
          </fieldset>
          <fieldset className="grid gap-4 md:grid-cols-2">
            <legend className="mb-2 text-sm font-semibold">Tax</legend>
            {text("Tax number", draft.tax_number, (tax_number) =>
              set({ tax_number }),
            )}
            {text("VAT id", draft.vat_id, (vat_id) => set({ vat_id }))}
            {text("Tax office", draft.tax_office, (tax_office) =>
              set({ tax_office }),
            )}
          </fieldset>
          <fieldset className="grid gap-4 md:grid-cols-2">
            <legend className="mb-2 text-sm font-semibold">Bank account</legend>
            {text("Account holder", draft.bank?.holder, (v) =>
              setBank("holder", v),
            )}
            {text("IBAN", draft.bank?.iban, (v) => setBank("iban", v))}
            {text("BIC", draft.bank?.bic, (v) => setBank("bic", v))}
            {text("Bank", draft.bank?.name, (v) => setBank("name", v))}
          </fieldset>
          <fieldset className="space-y-4">
            <legend className="mb-2 text-sm font-semibold">Sending mail</legend>
            <label className="flex min-h-5 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className={checkboxClass}
                checked={Boolean(draft.smtp)}
                onChange={(event) =>
                  event.target.checked ? setSmtp({}) : set({ smtp: null })
                }
              />
              Send mail as this identity (for example invoices to customers)
            </label>
            {draft.smtp && (
              <div className="grid gap-4 md:grid-cols-2">
                {text(
                  "Mail server (SMTP)",
                  draft.smtp.host,
                  (host) => setSmtp({ host }),
                  { required: true, placeholder: "smtp.example.org" },
                )}
                {text(
                  "Port",
                  String(draft.smtp.port ?? 587),
                  (port) => setSmtp({ port: Number(port) || 587 }),
                  { inputMode: "numeric" },
                )}
                {text("User name", draft.smtp.username, (username) =>
                  setSmtp({ username }),
                )}
                {text(
                  "Sender address",
                  draft.smtp.from_address,
                  (from_address) => setSmtp({ from_address }),
                  { required: true, type: "email" },
                )}
                {text(
                  "Password",
                  draft.smtp.password,
                  (password) => setSmtp({ password }),
                  {
                    type: "password",
                    autoComplete: "new-password",
                    placeholder:
                      editing !== null &&
                      items.find((p) => p.id === editing)?.has_smtp_password
                        ? "Stored; leave empty to keep it"
                        : "",
                  },
                )}
              </div>
            )}
          </fieldset>
          <label className="flex min-h-5 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className={checkboxClass}
              checked={Boolean(draft.shared)}
              onChange={(event) => set({ shared: event.target.checked })}
            />
            The household can use this identity
          </label>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              Save
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setDraft(null);
                setEditing(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </main>
  );
}
