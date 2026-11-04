import { describe, expect, it } from "vitest";
import { safeNext } from "../lib/auth";

describe("sign-in return path", () => {
  it("keeps local paths and rejects cross-origin and backslash redirects", () => {
    expect(safeNext("/documents?q=invoice")).toBe("/documents?q=invoice");
    for (const value of [
      "//evil.invalid",
      "https://evil.invalid",
      "/\\evil.invalid",
      "javascript:alert(1)",
      null,
    ])
      expect(safeNext(value)).toBe("/");
  });
});
