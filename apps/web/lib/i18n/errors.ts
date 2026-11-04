export const errors: Record<string, string> = {
  kb_not_found:
    "This knowledge base is unavailable. Refresh the list or create one.",
  kb_owner_required:
    "Only the owner can change this knowledge base. Create your own scope instead.",
  kb_invalid_filters:
    "Choose current categories, types and tags, and check the date range. Trashed documents cannot be included.",
  validation_error: "Check the supplied fields and try again.",
  local_consumer_session_required: "Sign in to mark a consumer as local-only.",
  api_unavailable: "The server is unavailable. Try again shortly.",
  csrf_required: "Your session needs to be refreshed. Reload and try again.",
  rate_limited: "Too many sign-in attempts. Try again in 15 minutes.",
  encrypted:
    "This file is password-protected. Download an unlocked copy and upload it again.",
  unsupported_type:
    "This file type is not supported. Use a PDF, image, Office file, email or text file.",
  vault_unavailable:
    "Your storage is unavailable. New files will stay safely in staging until it returns.",
};

export function errorMessage(code?: string): string {
  return (
    errors[code || ""] ||
    "Something went wrong. Try again, or check System status."
  );
}
