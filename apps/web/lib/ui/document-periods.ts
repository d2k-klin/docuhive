/** Complete calendar periods, using the browser's local date rather than UTC conversion. */
export function documentPeriod(
  period: "last_month" | "last_quarter",
  now = new Date(),
) {
  const month =
    period === "last_month"
      ? now.getMonth() - 1
      : Math.floor(now.getMonth() / 3) * 3 - 3;
  const start = new Date(now.getFullYear(), month, 1);
  const end = new Date(
    now.getFullYear(),
    month + (period === "last_month" ? 1 : 3),
    0,
  );
  const iso = (date: Date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  return { date_from: iso(start), date_to: iso(end) };
}
