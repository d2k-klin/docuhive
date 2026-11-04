import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const route of ["/login", "/dev/ui"]) {
  test(`UI ${route} @WEB-03 @WEB-04`, async ({ page }, info) => {
    await page.goto(route);
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
          name: el.getAttribute("aria-label") ?? el.id ?? el.tagName,
          height: el.getBoundingClientRect().height,
          expected: ["checkbox", "radio"].includes(
            (el as HTMLInputElement).type,
          )
            ? 16
            : el.dataset.size === "sm"
              ? 32
              : el.dataset.size === "lg"
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
