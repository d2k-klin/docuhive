import { expect, test } from "@playwright/test";

test("BFF streams SSE incrementally @smoke @WEB-01", async ({ page }) => {
  const login = await page.request.post("/api/auth/login", {
    headers: { "X-DocuHive-CSRF": "1" },
    data: { username: "alice", password: "synthetic qa password 2026" },
  });
  expect(login.status()).toBe(204);
  await page.goto("/");
  const ticks = await page.evaluate(async () => {
    const start = performance.now();
    const response = await fetch("/api/system/sse-test");
    if (!response.ok || !response.body)
      throw new Error("SSE endpoint unavailable");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const seen: { tick: number; elapsed: number }[] = [];
    let pending = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      let boundary: number;
      while ((boundary = pending.indexOf("\n\n")) >= 0) {
        const frame = pending.slice(0, boundary);
        pending = pending.slice(boundary + 2);
        const data = frame
          .split("\n")
          .find((line) => line.startsWith("data: "));
        if (data)
          seen.push({
            tick: JSON.parse(data.slice(6)).tick,
            elapsed: performance.now() - start,
          });
      }
    }
    return seen;
  });
  expect(ticks.map((event) => event.tick)).toEqual([
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
  ]);
  expect(ticks[0].elapsed).toBeLessThan(2000);
  expect(ticks[9].elapsed - ticks[0].elapsed).toBeGreaterThan(3000);
});
