import { redirect } from "next/navigation";
import { VocabularyPage } from "@/components/core/vocabulary";
import { serverClient } from "@/lib/api/server";

export default async function Vocabulary() {
  const me = await (await serverClient()).GET("/api/auth/me").catch(() => null);
  if (!me?.data) redirect("/login");
  return <VocabularyPage admin={me.data.role === "admin"} />;
}
