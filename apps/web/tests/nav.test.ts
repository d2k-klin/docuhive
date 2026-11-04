import { describe, expect, it } from "vitest";
import { visibleNav } from "../lib/nav";

describe("navigation permissions", () => {
  it("shows operations links only to administrators", () => {
    expect(visibleNav("member").some((item) => item.adminOnly)).toBe(false);
    expect(visibleNav("admin").some((item) => item.adminOnly)).toBe(true);
  });
});
