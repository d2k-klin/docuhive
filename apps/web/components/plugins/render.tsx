"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, CircleDashed, Inbox, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox, control } from "@/lib/ui/control";
import {
  ApiError,
  Badge,
  Card,
  Empty,
  ErrorBox,
  Field,
  Skeleton,
  formatDate,
  formatMoney,
} from "@/components/intel/common";

export type Text = string | Record<string, string>;
type Format =
  | "text"
  | "money"
  | "number"
  | "date"
  | "datetime"
  | "percent"
  | "badge"
  | "document"
  | "boolean";
type Action = {
  label: Text;
  action: string;
  when?: string;
  confirm?: Text;
  primary?: boolean;
  download?: boolean;
};
type Column = {
  field: string;
  label: Text;
  format: Format;
  align?: "left" | "right";
  total?: boolean;
  link?:
    | "document"
    | { page?: string; params?: Record<string, string>; document?: string };
  tones?: Record<string, string>;
};
type Filter = { field: string; type: string; label?: Text; options?: unknown };
type LineColumn = {
  name: string;
  label: Text;
  type?: string;
  required?: boolean;
};
type FormField = {
  name: string;
  type: string;
  label: Text;
  columns?: LineColumn[];
  required?: boolean;
  help?: Text;
  min?: number;
  max?: number;
  pattern?: string;
};
export type Block = {
  type: string;
  id?: string;
  title?: Text;
  help?: Text;
  text?: Text;
  columns?: Column[];
  filters?: Filter[];
  actions?: Action[];
  row_actions?: Action[];
  empty?: Text;
  select?: boolean;
  fields?: (FormField & { field?: string; format?: Format })[];
  submit?: Text;
  confirm?: Text;
  action?: string;
  x?: string;
  y?: string;
  kind?: "bar" | "line";
  format?: Format;
};
export type PageDescription = {
  plugin: string;
  plugin_name: string;
  title: Text;
  description?: Text;
  blocks: Block[];
};
type Row = Record<string, unknown>;
const NOWRAP: Format[] = ["date", "money", "number", "badge"];
type Option = { value: string; label: string };

/** A string from the plugin, in the reader's language when the plugin gives several. */
export function t(text: Text | undefined | null): string {
  if (text == null) return "";
  if (typeof text === "string") return text;
  const lang =
    typeof navigator === "undefined" ? "en" : navigator.language.slice(0, 2);
  return text[lang] ?? Object.values(text)[0] ?? "";
}

function base(plugin: string, page: string) {
  return `/api/plugin-pages/${encodeURIComponent(plugin)}/${encodeURIComponent(page)}`;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "X-DocuHive-CSRF": "1",
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = body.error ?? {};
    const error = new ApiError(
      err.code ?? `http_${res.status}`,
      err.message ?? "Something went wrong. Try again in a moment.",
      res.status,
    );
    (error as ApiError & { fields?: Record<string, string> }).fields =
      err.details?.fields;
    throw error;
  }
  if ((res.headers.get("Content-Type") || "").includes("application/json"))
    return (await res.json()) as T;
  return res as unknown as T;
}

function get(row: Row, field: string): unknown {
  let value: unknown = row;
  for (const part of field.split(".")) {
    value =
      value && typeof value === "object"
        ? (value as Record<string, unknown>)[part]
        : undefined;
  }
  return value;
}

function scalar(value: unknown): unknown {
  return value && typeof value === "object" && "value" in (value as object)
    ? (value as { value: unknown }).value
    : value;
}

function show(value: unknown, format: Format, row?: Row): React.ReactNode {
  const raw = scalar(value);
  if (raw == null || raw === "") return "—";
  switch (format) {
    case "money": {
      const currency =
        (value as { currency?: string })?.currency ??
        (row?.currency as string | undefined) ??
        "EUR";
      return formatMoney(String(raw), currency);
    }
    case "number":
      return new Intl.NumberFormat().format(Number(raw));
    case "percent":
      return `${new Intl.NumberFormat().format(Number(raw))} %`;
    case "date":
      return formatDate(String(raw));
    case "datetime":
      return new Date(String(raw)).toLocaleString();
    case "boolean":
      return raw ? "Yes" : "No";
    case "document":
      return (
        <Link
          href={`/documents/${encodeURIComponent(String(raw))}`}
          className="text-primary hover:underline"
        >
          Open
        </Link>
      );
    default:
      return String(raw);
  }
}

function href(plugin: string, link: Column["link"], row: Row): string | null {
  if (!link) return null;
  if (link === "document") return row.id ? `/documents/${row.id}` : null;
  if (link.document) {
    const id = get(row, link.document);
    return id ? `/documents/${id}` : null;
  }
  if (link.page) {
    const query = new URLSearchParams(
      Object.entries(link.params ?? {}).map(([k, f]) => [
        k,
        String(get(row, f) ?? ""),
      ]),
    );
    return `/plugins/${plugin}/${link.page}?${query}`;
  }
  return null;
}

/** Every block on the page reloads after any action changed something. */
const CHANGED = "docuhive-plugin-data-changed";
function changed() {
  window.dispatchEvent(new Event(CHANGED));
}

function useBlock<T>(url: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const bump = () => setTick((n) => n + 1);
    window.addEventListener(CHANGED, bump);
    return () => window.removeEventListener(CHANGED, bump);
  }, []);
  useEffect(() => {
    if (!url) return;
    let live = true;
    call<T>(url)
      .then((d) => live && (setData(d), setError(null)))
      .catch((e: ApiError) => live && setError(e));
    return () => {
      live = false;
    };
  }, [url, tick]);
  return { data, error, reload: useCallback(() => setTick((n) => n + 1), []) };
}

/** Runs an action, asks first when the plugin says so, and reports the outcome. */
async function runAction(
  plugin: string,
  page: string,
  action: Action,
  params: Row,
): Promise<{ message: string; goto?: string | null }> {
  if (action.confirm && !window.confirm(t(action.confirm)))
    return { message: "" };
  const res = await fetch(
    `${base(plugin, page)}/actions/${encodeURIComponent(action.action)}`,
    {
      method: "POST",
      headers: { "X-DocuHive-CSRF": "1", "Content-Type": "application/json" },
      body: JSON.stringify(params),
    },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      body.error?.code ?? "error",
      body.error?.message ?? "That did not work. Try again.",
      res.status,
    );
  }
  if (!(res.headers.get("Content-Type") || "").includes("application/json")) {
    const blob = await res.blob();
    const name =
      /filename="([^"]+)"/.exec(
        res.headers.get("Content-Disposition") || "",
      )?.[1] ?? "download";
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: name,
    });
    a.click();
    URL.revokeObjectURL(url);
    return { message: `Downloaded ${name}.` };
  }
  const out = await res.json();
  changed();
  return out;
}

export function PluginBlock({
  plugin,
  page,
  index,
  block,
  params,
  bare,
}: {
  plugin: string;
  page: string;
  index: number;
  block: Block;
  params: Record<string, string>;
  bare?: boolean;
}) {
  const body = (() => {
    switch (block.type) {
      case "text":
        return (
          <p className="max-w-prose whitespace-pre-line">{t(block.text)}</p>
        );
      case "summary":
        return (
          <Summary plugin={plugin} page={page} index={index} params={params} />
        );
      case "table":
        return (
          <Table
            plugin={plugin}
            page={page}
            index={index}
            block={block}
            params={params}
          />
        );
      case "detail":
        return (
          <Detail
            plugin={plugin}
            page={page}
            index={index}
            block={block}
            params={params}
          />
        );
      case "form":
        return (
          <Form
            plugin={plugin}
            page={page}
            index={index}
            block={block}
            params={params}
          />
        );
      case "actions":
        return (
          <Actions
            plugin={plugin}
            page={page}
            actions={block.actions ?? []}
            params={params}
          />
        );
      case "steps":
        return (
          <Steps
            plugin={plugin}
            page={page}
            index={index}
            block={block}
            params={params}
          />
        );
      case "chart":
        return (
          <Chart
            plugin={plugin}
            page={page}
            index={index}
            block={block}
            params={params}
          />
        );
      default:
        return null;
    }
  })();
  if (bare) return body;
  return (
    <Card title={t(block.title) || undefined}>
      {block.help && (
        <p className="mb-3 text-sm text-text-muted">{t(block.help)}</p>
      )}
      {body}
    </Card>
  );
}

function blockUrl(
  plugin: string,
  page: string,
  index: number,
  params: Record<string, string>,
) {
  return `${base(plugin, page)}/blocks/${index}?${new URLSearchParams(params)}`;
}

function Summary({
  plugin,
  page,
  index,
  params,
}: {
  plugin: string;
  page: string;
  index: number;
  params: Record<string, string>;
}) {
  const { data, error, reload } = useBlock<{
    items: {
      label: Text;
      value: unknown;
      format?: Format;
      hint?: Text;
      currency?: string;
    }[];
  }>(blockUrl(plugin, page, index, params));
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Skeleton rows={2} />;
  return (
    <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {data.items.map((item, i) => (
        <div key={i} className="min-w-0">
          <dt className="text-sm text-text-muted">{t(item.label)}</dt>
          <dd className="tabular break-words text-lg font-semibold">
            {show(item.value, item.format ?? "text", item as unknown as Row)}
          </dd>
          {item.hint && (
            <dd className="text-xs text-text-muted">{t(item.hint)}</dd>
          )}
        </div>
      ))}
    </dl>
  );
}

function Table({
  plugin,
  page,
  index,
  block,
  params,
}: {
  plugin: string;
  page: string;
  index: number;
  block: Block;
  params: Record<string, string>;
}) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState("");
  const [pageNo, setPageNo] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<string>("");
  const [failure, setFailure] = useState<ApiError | null>(null);
  const query = {
    ...params,
    ...filters,
    ...(sort ? { sort } : {}),
    page: String(pageNo),
  };
  const { data, error, reload } = useBlock<{
    rows: Row[];
    total: number;
    totals: Record<string, Record<string, string>>;
    options: Record<string, Option[]>;
  }>(blockUrl(plugin, page, index, query));
  const columns = block.columns ?? [];
  async function act(action: Action, rows: Row[]) {
    setFailure(null);
    try {
      const out = await runAction(plugin, page, action, {
        ...params,
        rows,
        ...(rows.length === 1 ? rows[0] : {}),
      });
      if (out.goto)
        window.location.assign(
          out.goto.startsWith("/")
            ? out.goto
            : `/plugins/${plugin}/${out.goto}`,
        );
      setNotice(out.message);
      setSelected(new Set());
    } catch (e) {
      setFailure(e as ApiError);
    }
  }
  return (
    <div className="space-y-3">
      {(block.filters ?? []).length > 0 && (
        <div
          role="group"
          aria-label="Filters"
          className="flex flex-wrap items-end gap-3"
        >
          {block.filters!.map((f) => (
            <label key={f.field} className="w-full sm:w-48">
              <span className="mb-1 block text-sm">
                {t(f.label) || f.field}
              </span>
              {f.type === "choice" || f.type === "boolean" ? (
                <select
                  className={control}
                  value={filters[f.field] ?? ""}
                  onChange={(e) => (
                    setFilters({ ...filters, [f.field]: e.target.value }),
                    setPageNo(0)
                  )}
                >
                  <option value="">All</option>
                  {(f.type === "boolean"
                    ? [
                        { value: "true", label: "Yes" },
                        { value: "false", label: "No" },
                      ]
                    : (data?.options[f.field] ?? [])
                  ).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  type={
                    f.type === "year"
                      ? "number"
                      : f.type === "date"
                        ? "date"
                        : "text"
                  }
                  value={filters[f.field] ?? ""}
                  onChange={(e) => (
                    setFilters({ ...filters, [f.field]: e.target.value }),
                    setPageNo(0)
                  )}
                />
              )}
            </label>
          ))}
        </div>
      )}
      {notice && (
        <p role="status" className="text-sm text-text-muted">
          {notice}
        </p>
      )}
      {failure && <ErrorBox error={failure} />}
      {error ? (
        <ErrorBox error={error} onRetry={reload} />
      ) : !data ? (
        <Skeleton rows={5} />
      ) : !data.rows.length ? (
        <Empty icon={Inbox} text={t(block.empty)} />
      ) : (
        <>
          {block.select &&
            (block.actions ?? []).length > 0 &&
            selected.size > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm">{selected.size} selected</span>
                {block.actions!.map((a) => (
                  <Button
                    key={a.action}
                    size="sm"
                    variant={a.primary ? "primary" : "secondary"}
                    onClick={() =>
                      void act(
                        a,
                        [...selected].map((i) => data.rows[i]),
                      )
                    }
                  >
                    {t(a.label)}
                  </Button>
                ))}
              </div>
            )}
          {/* Cards on phones, a table from tablet width. */}
          <ul className="space-y-2 md:hidden">
            {data.rows.map((row, i) => {
              const [first, ...rest] = columns;
              const link = href(plugin, first.link, row);
              return (
                <li key={i} className="rounded-card border border-border p-3">
                  <p className="break-words font-medium">
                    {link ? (
                      <Link href={link} className="underline">
                        {show(get(row, first.field), first.format, row)}
                      </Link>
                    ) : (
                      show(get(row, first.field), first.format, row)
                    )}
                  </p>
                  <dl className="mt-1 space-y-0.5 text-sm">
                    {rest.map((c) => (
                      <div key={c.field} className="flex justify-between gap-3">
                        <dt className="text-text-muted">{t(c.label)}</dt>
                        <dd className="tabular min-w-0 break-words text-right">
                          <Cell plugin={plugin} column={c} row={row} />
                        </dd>
                      </div>
                    ))}
                  </dl>
                  {(block.row_actions ?? []).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {block
                        .row_actions!.filter(
                          (a) => !a.when || scalar(get(row, a.when)),
                        )
                        .map((a) => (
                          <Button
                            key={a.action}
                            size="sm"
                            variant="secondary"
                            data-wrap
                            onClick={() => void act(a, [row])}
                          >
                            {t(a.label)}
                          </Button>
                        ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text-muted">
                  {block.select && (
                    <th className="w-8 px-2 py-2">
                      <input
                        type="checkbox"
                        className={checkbox}
                        aria-label="Select all on this page"
                        checked={selected.size === data.rows.length}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? new Set(data.rows.map((_, i) => i))
                              : new Set(),
                          )
                        }
                      />
                    </th>
                  )}
                  {columns.map((c) => (
                    <th
                      key={c.field}
                      className={`px-2 py-0 font-medium ${c.align === "right" || c.format === "money" ? "text-right" : ""}`}
                    >
                      <button
                        type="button"
                        data-size="sm"
                        className="inline-flex h-control-sm items-center hover:underline"
                        onClick={() =>
                          setSort(sort === c.field ? `-${c.field}` : c.field)
                        }
                        aria-label={`Sort by ${t(c.label)}`}
                      >
                        {t(c.label)}
                        {sort.replace("-", "") === c.field &&
                          (sort.startsWith("-") ? " ↓" : " ↑")}
                      </button>
                    </th>
                  ))}
                  {(block.row_actions ?? []).length > 0 && (
                    <th className="px-2 py-2">
                      <span className="sr-only">Actions</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i} className="border-b border-border">
                    {block.select && (
                      <td className="px-2 py-2">
                        <input
                          type="checkbox"
                          className={checkbox}
                          aria-label={`Select row ${i + 1}`}
                          checked={selected.has(i)}
                          onChange={(e) => {
                            const next = new Set(selected);
                            if (e.target.checked) next.add(i);
                            else next.delete(i);
                            setSelected(next);
                          }}
                        />
                      </td>
                    )}
                    {columns.map((c) => (
                      <td
                        key={c.field}
                        className={`max-w-xs px-2 py-2 ${NOWRAP.includes(c.format) ? "whitespace-nowrap" : "break-words"} ${c.align === "right" || c.format === "money" ? "tabular text-right" : ""}`}
                      >
                        <Cell plugin={plugin} column={c} row={row} />
                      </td>
                    ))}
                    {(block.row_actions ?? []).length > 0 && (
                      <td className="px-2 py-2 text-right">
                        <div className="flex flex-wrap justify-end gap-2">
                          {block
                            .row_actions!.filter(
                              (a) => !a.when || scalar(get(row, a.when)),
                            )
                            .map((a) => (
                              <Button
                                key={a.action}
                                size="sm"
                                variant="secondary"
                                data-wrap
                                onClick={() => void act(a, [row])}
                              >
                                {t(a.label)}
                              </Button>
                            ))}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
              {Object.keys(data.totals).length > 0 && (
                <tfoot>
                  <tr className="font-medium">
                    {block.select && <td />}
                    {columns.map((c, i) => (
                      <td
                        key={c.field}
                        className={`px-2 py-2 ${c.format === "money" ? "tabular text-right" : ""}`}
                      >
                        {data.totals[c.field]
                          ? Object.entries(data.totals[c.field])
                              .map(([cur, v]) =>
                                c.format === "money"
                                  ? formatMoney(v, cur || "EUR")
                                  : v,
                              )
                              .join(" · ")
                          : i === 0
                            ? "Total"
                            : ""}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          {data.total > data.rows.length && (
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <Button
                size="sm"
                variant="secondary"
                disabled={pageNo === 0}
                onClick={() => setPageNo(pageNo - 1)}
              >
                Previous
              </Button>
              <span>
                {pageNo * data.rows.length + 1}–
                {pageNo * data.rows.length + data.rows.length} of {data.total}
              </span>
              <Button
                size="sm"
                variant="secondary"
                disabled={(pageNo + 1) * data.rows.length >= data.total}
                onClick={() => setPageNo(pageNo + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Cell({
  plugin,
  column,
  row,
}: {
  plugin: string;
  column: Column;
  row: Row;
}) {
  const value = get(row, column.field);
  if (column.format === "badge") {
    const raw = String(scalar(value) ?? "");
    const tone = (column.tones?.[raw] ?? "muted") as
      "ok" | "warn" | "error" | "info" | "muted";
    return raw ? <Badge tone={tone}>{raw}</Badge> : <>—</>;
  }
  const link = href(plugin, column.link, row);
  const shown = show(value, column.format, row);
  return link ? (
    <Link href={link} className="underline">
      {shown}
    </Link>
  ) : (
    <>{shown}</>
  );
}

function Detail({
  plugin,
  page,
  index,
  block,
  params,
}: {
  plugin: string;
  page: string;
  index: number;
  block: Block;
  params: Record<string, string>;
}) {
  const { data, error, reload } = useBlock<{ record: Row }>(
    blockUrl(plugin, page, index, params),
  );
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Skeleton rows={3} />;
  return (
    <dl className="space-y-3">
      {(block.fields ?? []).map((f) => (
        <div key={f.field ?? f.name}>
          <dt className="text-sm text-text-muted">{t(f.label)}</dt>
          <dd className="break-words">
            {show(
              get(data.record, f.field ?? f.name),
              f.format ?? "text",
              data.record,
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Form({
  plugin,
  page,
  index,
  block,
  params,
}: {
  plugin: string;
  page: string;
  index: number;
  block: Block;
  params: Record<string, string>;
}) {
  const { data, error, reload } = useBlock<{
    initial: Row;
    options: Record<string, Option[]>;
  }>(blockUrl(plugin, page, index, params));
  const [values, setValues] = useState<Row | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const current = values ?? data?.initial ?? {};
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (block.confirm && !window.confirm(t(block.confirm))) return;
    setBusy(true);
    setFailure(null);
    setMessage("");
    try {
      const out = await call<{ message: string; goto?: string | null }>(
        `${base(plugin, page)}/actions/${encodeURIComponent(block.action ?? "")}`,
        { method: "POST", body: JSON.stringify({ ...params, ...current }) },
      );
      setFieldErrors({});
      setValues(null);
      setMessage(out.message);
      changed();
      if (out.goto)
        window.location.assign(
          out.goto.startsWith("/")
            ? out.goto
            : `/plugins/${plugin}/${out.goto}`,
        );
    } catch (e) {
      const err = e as ApiError & { fields?: Record<string, string> };
      setFieldErrors(err.fields ?? {});
      setFailure(err);
    } finally {
      setBusy(false);
    }
  }
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Skeleton rows={3} />;
  const set = (name: string, value: unknown) =>
    setValues({ ...current, [name]: value });
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {(block.fields ?? []).map((f) => {
        const value = current[f.name];
        const problem = fieldErrors[f.name];
        const label = t(f.label) + (f.required ? " (required)" : "");
        const help = [t(f.help), problem].filter(Boolean).join(" ");
        if (f.type === "lines")
          return (
            <Lines
              key={f.name}
              field={f}
              label={label}
              help={help}
              rows={Array.isArray(value) ? (value as Row[]) : []}
              options={data.options}
              onChange={(rows) => set(f.name, rows)}
            />
          );
        if (f.type === "boolean")
          return (
            <label key={f.name} className="flex min-h-5 items-center gap-2">
              <input
                type="checkbox"
                className={checkbox}
                checked={Boolean(value)}
                onChange={(e) => set(f.name, e.target.checked)}
              />
              {label}
            </label>
          );
        return (
          <Field key={f.name} label={label} help={help || undefined}>
            {f.type === "choice" ? (
              <select
                className={control}
                aria-invalid={Boolean(problem)}
                value={String(value ?? "")}
                onChange={(e) => set(f.name, e.target.value)}
              >
                <option value="">Choose…</option>
                {(data.options[f.name] ?? []).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : f.type === "textarea" ? (
              <textarea
                className={`${control} h-auto min-h-24 py-2`}
                aria-invalid={Boolean(problem)}
                value={String(value ?? "")}
                onChange={(e) => set(f.name, e.target.value)}
              />
            ) : (
              <Input
                aria-invalid={Boolean(problem)}
                type={
                  f.type === "date"
                    ? "date"
                    : f.type === "number" || f.type === "money"
                      ? "number"
                      : "text"
                }
                step={f.type === "money" ? "0.01" : undefined}
                min={f.min}
                max={f.max}
                pattern={f.pattern}
                required={f.required}
                value={String(value ?? "")}
                onChange={(e) => set(f.name, e.target.value)}
              />
            )}
          </Field>
        );
      })}
      {failure && !Object.keys(fieldErrors).length && (
        <ErrorBox error={failure} />
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : t(block.submit) || "Save"}
        </Button>
        {message && (
          <span role="status" className="text-sm text-text-muted">
            {message}
          </span>
        )}
      </div>
    </form>
  );
}

/** A repeating group, such as invoice lines: one row per entry, add and remove. */
function Lines({
  field,
  label,
  help,
  rows,
  options,
  onChange,
}: {
  field: FormField;
  label: string;
  help: string;
  rows: Row[];
  options: Record<string, Option[]>;
  onChange: (rows: Row[]) => void;
}) {
  const columns = field.columns ?? [];
  const blank = () => Object.fromEntries(columns.map((c) => [c.name, ""]));
  const shown = rows.length ? rows : [blank()];
  const update = (index: number, name: string, value: string) =>
    onChange(shown.map((r, i) => (i === index ? { ...r, [name]: value } : r)));
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">{label}</legend>
      {help && <p className="text-xs text-text-muted">{help}</p>}
      {shown.map((row, index) => (
        <div
          key={index}
          className="grid gap-2 rounded-card border border-border p-2 md:grid-cols-[repeat(auto-fit,minmax(8rem,1fr))]"
        >
          {columns.map((c) => (
            <label key={c.name} className="space-y-1 text-xs text-text-muted">
              {t(c.label)}
              {c.type === "choice" ? (
                <select
                  className={control}
                  value={String(row[c.name] ?? "")}
                  onChange={(e) => update(index, c.name, e.target.value)}
                >
                  <option value="">Choose…</option>
                  {(options[`${field.name}.${c.name}`] ?? []).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  type={
                    c.type === "number" || c.type === "money"
                      ? "number"
                      : "text"
                  }
                  step={
                    c.type === "money"
                      ? "0.01"
                      : c.type === "number"
                        ? "any"
                        : undefined
                  }
                  value={String(row[c.name] ?? "")}
                  onChange={(e) => update(index, c.name, e.target.value)}
                />
              )}
            </label>
          ))}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="self-end"
            aria-label={`Remove line ${index + 1}`}
            onClick={() => onChange(shown.filter((_, i) => i !== index))}
          >
            Remove
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => onChange([...shown, blank()])}
      >
        Add a line
      </Button>
    </fieldset>
  );
}

function Actions({
  plugin,
  page,
  actions,
  params,
}: {
  plugin: string;
  page: string;
  actions: Action[];
  params: Record<string, string>;
}) {
  const [message, setMessage] = useState("");
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <Button
            key={a.action}
            variant={a.primary ? "primary" : "secondary"}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setFailure(null);
              try {
                const out = await runAction(plugin, page, a, params);
                setMessage(out.message);
                if (out.goto)
                  window.location.assign(
                    out.goto.startsWith("/")
                      ? out.goto
                      : `/plugins/${plugin}/${out.goto}`,
                  );
              } catch (e) {
                setFailure(e as ApiError);
              } finally {
                setBusy(false);
              }
            }}
          >
            {t(a.label)}
          </Button>
        ))}
      </div>
      {message && (
        <p role="status" className="text-sm text-text-muted">
          {message}
        </p>
      )}
      {failure && <ErrorBox error={failure} />}
    </div>
  );
}

function Steps({
  plugin,
  page,
  index,
  block,
  params,
}: {
  plugin: string;
  page: string;
  index: number;
  block: Block;
  params: Record<string, string>;
}) {
  const { data, error, reload } = useBlock<{
    items: { label: Text; state: "done" | "todo" | "problem"; link?: string }[];
  }>(blockUrl(plugin, page, index, params));
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Skeleton rows={3} />;
  if (!data.items.length)
    return (
      <p className="text-sm text-text-muted">
        {t(block.empty) || "Nothing left to do."}
      </p>
    );
  const icon = {
    done: CheckCircle2,
    todo: CircleDashed,
    problem: TriangleAlert,
  };
  const tone = {
    done: "text-success",
    todo: "text-text-muted",
    problem: "text-warning",
  };
  return (
    <ul className="divide-y divide-border">
      {data.items.map((item, i) => {
        const Icon = icon[item.state] ?? CircleDashed;
        return (
          <li key={i} className="flex items-start gap-2 py-2">
            <Icon
              aria-hidden="true"
              className={`mt-0.5 size-4 shrink-0 ${tone[item.state] ?? ""}`}
            />
            <span className="min-w-0 break-words">
              {item.link ? (
                <Link className="underline" href={item.link}>
                  {t(item.label)}
                </Link>
              ) : (
                t(item.label)
              )}
              <span className="sr-only"> ({item.state})</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Chart({
  plugin,
  page,
  index,
  block,
  params,
}: {
  plugin: string;
  page: string;
  index: number;
  block: Block;
  params: Record<string, string>;
}) {
  const { data, error, reload } = useBlock<{ items: Row[] }>(
    blockUrl(plugin, page, index, params),
  );
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Skeleton rows={4} />;
  if (!data.items.length)
    return (
      <p className="text-sm text-text-muted">
        {t(block.empty) || "Nothing to show yet."}
      </p>
    );
  const x = block.x ?? "x";
  const y = block.y ?? "y";
  const values = data.items.map((r) => Number(scalar(get(r, y))) || 0);
  const max = Math.max(...values, 0) || 1;
  const width = 600;
  const height = 200;
  const step = width / values.length;
  const fmt = block.format ?? "number";
  return (
    <figure>
      <svg
        viewBox={`0 0 ${width} ${height + 20}`}
        role="img"
        aria-label={t(block.title) || "Chart"}
        className="w-full"
      >
        {block.kind === "line" ? (
          <polyline
            fill="none"
            stroke="currentColor"
            className="text-primary"
            strokeWidth={2}
            points={values
              .map(
                (v, i) =>
                  `${i * step + step / 2},${height - (v / max) * height}`,
              )
              .join(" ")}
          />
        ) : (
          values.map((v, i) => (
            <rect
              key={i}
              x={i * step + step * 0.15}
              y={height - (v / max) * height}
              width={step * 0.7}
              height={(v / max) * height}
              className="fill-primary"
            />
          ))
        )}
        {data.items.map((r, i) => (
          <text
            key={i}
            x={i * step + step / 2}
            y={height + 14}
            textAnchor="middle"
            className="fill-text-muted text-[10px]"
          >
            {String(scalar(get(r, x)) ?? "")}
          </text>
        ))}
      </svg>
      <table className="sr-only">
        <tbody>
          {data.items.map((r, i) => (
            <tr key={i}>
              <th>{String(scalar(get(r, x)) ?? "")}</th>
              <td>{show(get(r, y), fmt, r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
