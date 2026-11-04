import { expect, test } from "@playwright/test";

test("sign in and sign out through the actual same-origin proxy", async ({ page }) => {
  test.skip(!process.env.DOCUHIVE_UI_TEST_PASSWORD, "Requires a synthetic account in the isolated test API.");
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Username").fill(process.env.DOCUHIVE_UI_TEST_USER || "oa_browser");
  await page.getByLabel("Password", { exact: true }).fill(process.env.DOCUHIVE_UI_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  const initial = await page.locator("html").getAttribute("class");
  await page.getByRole("button", { name: /^Switch to (light|dark) theme$/ }).click();
  await expect.poll(() => page.locator("html").getAttribute("class")).not.toBe(initial);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
});
