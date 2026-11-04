"use client";

import type { components } from "@/lib/api/schema";
import { Input } from "@/components/ui/input";
import { checkbox as checkboxClass } from "@/lib/ui/control";

type Filters = components["schemas"]["SearchFilters"];
type Taxonomy = components["schemas"]["Taxonomy"];
export const emptyFilters: Filters = {
  categories: [],
  document_types: [],
  correspondents: [],
  tags: [],
  source_kinds: [],
  document_ids: [],
  include_trashed: false,
};

export function DocumentFilters({
  value,
  taxonomy,
  onChange,
}: {
  value: Filters;
  taxonomy: Taxonomy;
  onChange: (value: Filters) => void;
}) {
  function choices(
    label: string,
    field: "categories" | "document_types" | "tags" | "source_kinds",
    options: { id: string; label: string }[],
  ) {
    const selected = value[field] || [];
    return (
      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-medium">{label}</legend>
        <div className="flex max-h-48 flex-wrap gap-x-6 gap-y-2 overflow-auto">
          {options.map((option) => (
            <label
              key={option.id}
              className="flex min-h-5 items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                className={checkboxClass}
                checked={(selected as string[]).includes(option.id)}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...selected, option.id]
                    : selected.filter((id) => id !== option.id);
                  onChange({ ...value, [field]: next });
                }}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
    );
  }
  return (
    <div className="space-y-4">
      <p className="text-xs text-text-muted">
        Leave a filter empty to include everything in that field. Categories
        include their subcategories.
      </p>
      {choices("Categories", "categories", taxonomy.categories)}
      {choices("Document types", "document_types", taxonomy.document_types)}
      {taxonomy.tags.length > 0 &&
        choices(
          "Tags",
          "tags",
          taxonomy.tags.map((tag) => ({ id: tag, label: tag })),
        )}
      {choices("Sources", "source_kinds", [
        { id: "upload", label: "Web upload" },
        { id: "mobile", label: "Phone" },
        { id: "email", label: "Email" },
        { id: "consume", label: "Scanner folder" },
        { id: "api", label: "API upload" },
      ])}
      <label className="block space-y-1.5 text-sm font-medium">
        Correspondents
        <Input
          value={(value.correspondents || []).join(",")}
          onChange={(event) =>
            onChange({
              ...value,
              correspondents: event.target.value.split(","),
            })
          }
          placeholder="Names, separated by commas"
        />
      </label>
      <div className="grid gap-4 lg:grid-cols-2">
        <label className="block space-y-1.5 text-sm font-medium">
          From date
          <Input
            type="date"
            value={value.date_from || ""}
            max={value.date_to || undefined}
            onChange={(event) =>
              onChange({ ...value, date_from: event.target.value || null })
            }
          />
        </label>
        <label className="block space-y-1.5 text-sm font-medium">
          To date
          <Input
            type="date"
            value={value.date_to || ""}
            min={value.date_from || undefined}
            onChange={(event) =>
              onChange({ ...value, date_to: event.target.value || null })
            }
          />
        </label>
      </div>
    </div>
  );
}
