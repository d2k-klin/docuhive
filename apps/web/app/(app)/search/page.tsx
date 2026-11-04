import { SearchPage } from "@/components/core/search";

export default async function Search({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  return <SearchPage initial={typeof q === "string" ? q.slice(0, 500) : ""} />;
}
