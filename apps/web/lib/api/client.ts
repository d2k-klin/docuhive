import createClient from "openapi-fetch";
import type { paths } from "./schema";

export function browserClient() {
  return createClient<paths>({
    baseUrl: "",
    headers: { "X-DocuHive-CSRF": "1" },
  });
}
