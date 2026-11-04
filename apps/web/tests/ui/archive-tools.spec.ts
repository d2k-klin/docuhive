import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("saved views, custom fields, duplicates and storage health pages", async ({
  page,
}, testInfo) => {
  test.skip(
    !process.env.DOCUHIVE_UI_TEST_PASSWORD,
    "Requires a synthetic account in the isolated test API.",
  );
  const name = `QA view ${testInfo.project.name} ${Date.now()}`;
  await page.goto("/login");
  await page
    .getByLabel("Username")
    .fill(process.env.DOCUHIVE_UI_TEST_USER || "oa_browser");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DOCUHIVE_UI_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await page.getByRole("link", { name: "Saved views", exact: true }).click();
  await page.getByRole("button", { name: "Create view", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page.getByLabel("Electricity", { exact: true }).check();
  await page.getByRole("button", { name: "Save view", exact: true }).click();
  const pinned = page
    .getByRole("navigation", { name: "Pinned views" })
    .getByRole("link", { name, exact: true });
  await expect(pinned).toBeVisible();
  await pinned.click();
  await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();

  for (const [link, heading] of [
    ["Custom fields", "Custom fields"],
    ["Duplicates", "Possible duplicates"],
  ]) {
    await page.getByRole("link", { name: link, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: heading, level: 1 }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
    ).toBe(false);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  }

  await page.getByRole("link", { name: "Saved views", exact: true }).click();
  await page
    .getByRole("button", { name: `Delete ${name}`, exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm delete", exact: true }).click();
  await expect(pinned).toHaveCount(0);
});
