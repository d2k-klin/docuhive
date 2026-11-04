import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("foundation page has readable type, no overflow and accessible structure", async ({
  page,
}, testInfo) => {
  await page.goto("/login");
  if (testInfo.project.name.endsWith("dark"))
    await page.locator("html").evaluate((el) => el.classList.add("dark"));
  await expect(
    page.getByRole("heading", { name: "Sign in to DocuHive", exact: true }),
  ).toBeVisible();
  const metrics = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > window.innerWidth,
    titleSize: getComputedStyle(document.querySelector("h1")!).fontSize,
    bodySize: getComputedStyle(document.body).fontSize,
  }));
  expect(metrics).toEqual({
    overflow: false,
    titleSize: "20px",
    bodySize: "14px",
  });
  const analysis = await new AxeBuilder({ page }).analyze();
  expect(analysis.violations).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("foundation.png"),
    fullPage: true,
  });
});
