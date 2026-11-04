export const errors: Record<string, string> = {
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
