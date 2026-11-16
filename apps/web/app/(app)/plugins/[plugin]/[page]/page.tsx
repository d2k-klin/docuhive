import { PluginPage } from "@/components/plugins/plugin-page";

export default async function PluginRoute({
  params,
  searchParams,
}: {
  params: Promise<{ plugin: string; page: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { plugin, page } = await params;
  const query = Object.fromEntries(
    Object.entries(await searchParams).flatMap(([k, v]) =>
      typeof v === "string" ? [[k, v]] : [],
    ),
  );
  return (
    <PluginPage
      key={`${plugin}/${page}`}
      plugin={plugin}
      page={page}
      params={query}
    />
  );
}
