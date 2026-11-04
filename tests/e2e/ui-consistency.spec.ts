import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const routes = [
  "/login",
  "/",
  "/review",
  "/ask",
  "/analyses",
  "/sources",
  "/reminders",
  "/settings/ai",
  "/settings/notifications",
];

test("Development UI is unavailable in production @smoke @NFR-02", async ({
  page,
}) => {
  const login = await page.request.post("/api/auth/login", {
    headers: { "X-DocuHive-CSRF": "1" },
    data: { username: "alice", password: "synthetic qa password 2026" },
  });
  expect(login.status()).toBe(204);
  expect((await page.request.get("/dev/ui")).status()).toBe(404);
});

for (const route of routes) {
  test(`UI ${route} @WEB-03 @WEB-04`, async ({ page }, info) => {
    if (route !== "/login") {
      const login = await page.request.post("/api/auth/login", {
        headers: { "X-DocuHive-CSRF": "1" },
        data: { username: "alice", password: "synthetic qa password 2026" },
      });
      expect(login.status()).toBe(204);
    }
    await page.goto(route);
    await expect.poll(() => new URL(page.url()).pathname).toBe(route);
    await page.evaluate(() => document.fonts.ready);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    const measurements = await page.evaluate(() => {
      const controls = Array.from(
        document.querySelectorAll<HTMLElement>(
          'button, input:not([type="hidden"]), select, [role="combobox"]',
        ),
      )
        .filter((el) => el.getBoundingClientRect().height > 0)
        .map((el) => ({
          name:
            el.getAttribute("aria-label") ||
            el.id ||
            el.textContent?.trim() ||
            el.tagName,
          height: el.getBoundingClientRect().height,
          // Wrapping controls (tag input, suggestion chips) have a min-height, not a height.
          wrap: el.hasAttribute("data-wrap"),
          expected: ["checkbox", "radio"].includes(
            (el as HTMLInputElement).type,
          )
            ? 16
            : el.dataset.size === "sm" || el.classList.contains("h-control-sm")
              ? 32
              : el.dataset.size === "lg" ||
                  el.classList.contains("h-control-lg")
                ? 40
                : 36,
        }));
      return {
        controls,
        overflow:
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth,
        headings: Array.from(document.querySelectorAll("h1,h2,h3")).map(
          (el) => ({
            size: parseFloat(getComputedStyle(el).fontSize),
            weight: getComputedStyle(el).fontWeight,
          }),
        ),
        expectedFont: getComputedStyle(document.body)
          .getPropertyValue("--font-inter")
          .split(",")[0]
          .trim()
          .replaceAll('"', ""),
        fonts: [
          ...new Set(
            Array.from(document.querySelectorAll("button,input,h1,h2,p")).map(
              (el) => getComputedStyle(el).fontFamily,
            ),
          ),
        ],
      };
    });
    await info.attach("measurements", {
      body: JSON.stringify(measurements, null, 2),
      contentType: "application/json",
    });
    expect(measurements.overflow).toBe(false);
    for (const control of measurements.controls)
      if (control.wrap)
        expect(control.height, control.name).toBeGreaterThanOrEqual(
          control.expected - 0.5,
        );
      else
        expect(
          Math.abs(control.height - control.expected),
          control.name,
        ).toBeLessThanOrEqual(0.5);
    for (const heading of measurements.headings) {
      expect(heading.size).toBeLessThanOrEqual(20);
      expect(heading.weight).toBe("600");
    }
    // Next's localFont hashes family names; compare against the actual Inter token.
    expect(measurements.expectedFont).not.toBe("");
    expect(
      measurements.fonts.every(
        (font) =>
          font.split(",")[0].trim().replaceAll('"', "") ===
          measurements.expectedFont,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath("page.png"),
      fullPage: true,
    });
  });
}
