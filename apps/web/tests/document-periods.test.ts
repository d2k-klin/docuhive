import { describe, expect, it } from "vitest";
import { documentPeriod } from "../lib/ui/document-periods";

describe("document calendar groups", () => {
  it("uses the previous complete month and calendar quarter", () => {
    const now = new Date(2026, 10, 5);
    expect(documentPeriod("last_month", now)).toEqual({
      date_from: "2026-10-01",
      date_to: "2026-10-31",
    });
    expect(documentPeriod("last_quarter", now)).toEqual({
      date_from: "2026-07-01",
      date_to: "2026-09-30",
    });
  });
  it("crosses years and includes leap-year February", () => {
    expect(documentPeriod("last_quarter", new Date(2026, 0, 5))).toEqual({
      date_from: "2025-10-01",
      date_to: "2025-12-31",
    });
    expect(documentPeriod("last_month", new Date(2024, 2, 5))).toEqual({
      date_from: "2024-02-01",
      date_to: "2024-02-29",
    });
  });
});
