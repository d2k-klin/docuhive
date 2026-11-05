export const errors: Record<string, string> = {
  document_disabled_category:
    "This category is no longer enabled. Choose another category, or ask an administrator to enable it.",
  category_unknown: "A category changed. Reload the list and choose again.",
  category_required: "Choose at least one category for your documents.",
  category_name_required: "Give your category a name.",
  category_exists:
    "That category already exists here. Choose it from the list.",
  category_parent_unknown: "Choose an enabled parent category, or no parent.",
  category_limit:
    "You can have up to 500 categories. Use an existing category.",
  too_large:
    "These files are too large. Choose fewer pages or smaller files and try again.",
  intake_unavailable:
    "Document intake is unavailable. Your queued files are kept on this device. Try again later.",
  kb_not_found:
    "This knowledge base is unavailable. Refresh the list or create one.",
  kb_owner_required:
    "Only the owner can change this knowledge base. Create your own scope instead.",
  kb_invalid_filters:
    "Choose current categories, types and tags, and check the date range. Trashed documents cannot be included.",
  view_not_found: "This saved view is unavailable. Refresh the list.",
  view_owner_required:
    "Only the owner can change this view. Save your own copy instead.",
  field_not_found: "This custom field no longer exists. Refresh the list.",
  field_name_taken: "Another custom field already uses this name.",
  field_name_builtin:
    "A built-in field already uses this name. Choose another name.",
  field_unknown_type: "Choose document types from the current list.",
  field_reminder_needs_date: "Only date fields can have reminders.",
  duplicate_not_found:
    "This pair was already decided. Refresh the list to see what is left.",
  export_empty:
    "No documents match this filter, so there is nothing to export.",
  export_too_large:
    "Exports are limited to 1000 documents. Narrow the filter, for example to one year.",
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
