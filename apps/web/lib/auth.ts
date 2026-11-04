export function safeNext(value: string | null): string {
  const base = "https://docuhive.invalid";
  try {
    const url = new URL(value || "/", base);
    return url.origin === base ? url.pathname + url.search + url.hash : "/";
  } catch {
    return "/";
  }
}
