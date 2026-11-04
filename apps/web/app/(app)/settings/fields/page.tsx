import { redirect } from "next/navigation";
import { CustomFields } from "@/components/core/custom-fields";
import { serverClient } from "@/lib/api/server";

export default async function FieldsPage() {
  const api = await serverClient();
  const [{ data }, fields, taxonomy] = await Promise.all([
    api.GET("/api/auth/me"),
    api.GET("/api/custom-fields").catch(() => null),
    api.GET("/api/kb/options").catch(() => null),
  ]);
  if (!data) redirect("/login");
  return (
    <CustomFields
      admin={data.role === "admin"}
      initial={fields?.data || null}
      documentTypes={taxonomy?.data?.document_types || null}
    />
  );
}
