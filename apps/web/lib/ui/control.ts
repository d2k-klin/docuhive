export const control =
  "h-control w-full rounded border border-[var(--border)] bg-[var(--surface)] px-[var(--control-px)] " +
  "text-[length:var(--text-base)] text-[var(--text)] placeholder:text-[var(--text-subtle)] " +
  "transition-colors hover:border-[var(--border-strong)] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:border-[var(--primary)] " +
  "disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-[var(--danger)]";
export const controlSm = control.replace("h-control", "h-control-sm");
export const checkbox =
  "size-[var(--check-size)] shrink-0 accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";
