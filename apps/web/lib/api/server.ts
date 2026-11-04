import { cookies } from "next/headers";
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export async function serverClient() {
  const session = (await cookies()).get("dh_session");
  return createClient<paths>({
    baseUrl: process.env.DOCUHIVE_API_URL || "http://127.0.0.1:8000",
    headers: session
      ? { cookie: `dh_session=${session.value}`, "X-DocuHive-CSRF": "1" }
      : { "X-DocuHive-CSRF": "1" },
    cache: "no-store",
  });
}
