"use client";

import { useEffect, useState } from "react";
import { Puzzle } from "lucide-react";
import {
  ApiError,
  Card,
  Empty,
  ErrorBox,
  Page,
  PageHeader,
  Skeleton,
} from "@/components/intel/common";
import { PluginBlock, t, type PageDescription } from "./render";

type Slot = {
  plugin: string;
  plugin_name: string;
  page: string;
  description: PageDescription;
};

async function load<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { "X-DocuHive-CSRF": "1" } });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      body.error?.code ?? "error",
      body.error?.message ?? "This page could not be loaded.",
      res.status,
    );
  }
  return res.json();
}

function useLoad<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let live = true;
    load<T>(url)
      .then((d) => live && setData(d))
      .catch((e: ApiError) => live && setError(e));
    return () => {
      live = false;
    };
  }, [url]);
  return { data, error };
}

/** A plugin's page, drawn from its YAML description. */
export function PluginPage({
  plugin,
  page,
  params,
}: {
  plugin: string;
  page: string;
  params: Record<string, string>;
}) {
  const { data, error } = useLoad<PageDescription>(
    `/api/plugin-pages/${encodeURIComponent(plugin)}/${encodeURIComponent(page)}`,
  );
  if (error)
    return (
      <Page>
        {error.status === 404 ? (
          <Empty
            icon={Puzzle}
            text="This page is not available. The plugin may be switched off, or the page is for administrators."
          />
        ) : (
          <ErrorBox error={error} />
        )}
      </Page>
    );
  if (!data)
    return (
      <Page>
        <Skeleton rows={6} />
      </Page>
    );
  return (
    <Page>
      <PageHeader
        title={t(data.title)}
        description={t(data.description) || undefined}
      />
      <div className="space-y-4">
        {data.blocks.map((block, i) => (
          <PluginBlock
            key={i}
            plugin={plugin}
            page={page}
            index={i}
            block={block}
            params={params}
          />
        ))}
      </div>
    </Page>
  );
}

/** One card per running plugin that has a `_dashboard.yaml`. */
export function PluginDashboardCards() {
  const { data } = useLoad<Slot[]>("/api/plugin-pages/slots/dashboard");
  if (!data?.length) return null;
  return (
    <>
      {data.map((slot) => (
        <Card
          key={slot.plugin}
          title={t(slot.description.title) || slot.plugin_name}
        >
          <PluginBlock
            plugin={slot.plugin}
            page="_dashboard"
            index={0}
            block={slot.description.blocks[0]}
            params={{}}
            bare
          />
        </Card>
      ))}
    </>
  );
}

/** Panels from plugins whose `_document.yaml` is for this kind of document. */
export function PluginDocumentPanels({ documentId }: { documentId: string }) {
  const { data } = useLoad<Slot[]>(
    `/api/plugin-pages/slots/document/${encodeURIComponent(documentId)}`,
  );
  if (!data?.length) return null;
  return (
    <>
      {data.map((slot) => (
        <Card
          key={slot.plugin}
          title={t(slot.description.title) || slot.plugin_name}
        >
          <div className="space-y-4">
            {slot.description.blocks.map((block, i) => (
              <PluginBlock
                key={i}
                plugin={slot.plugin}
                page="_document"
                index={i}
                block={block}
                params={{ document_id: documentId }}
                bare
              />
            ))}
          </div>
        </Card>
      ))}
    </>
  );
}
