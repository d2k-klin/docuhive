import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("manage a knowledge base and scoped token through the real API", async ({
  page,
}, testInfo) => {
  test.skip(
    !process.env.DOCUHIVE_UI_TEST_PASSWORD,
    "Requires a synthetic account in the isolated test API.",
  );
  const name =
    `QA ${testInfo.project.name} ${Date.now()} ${"document scope ".repeat(4)}`.trim();
  await page.goto("/login");
  await page
    .getByLabel("Username")
    .fill(process.env.DOCUHIVE_UI_TEST_USER || "oa_browser");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DOCUHIVE_UI_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("link", { name: "Knowledge bases", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Create knowledge base", exact: true })
    .click();
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page
    .getByLabel("Description", { exact: true })
    .fill("Synthetic browser journey");
  await page.getByLabel("Electricity", { exact: true }).check();
  await page.getByLabel("Share this knowledge base", { exact: true }).check();
  await page
    .getByRole("button", { name: "Save knowledge base", exact: true })
    .click();
  const base = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name, exact: true }) });
  await expect(base.getByText("Shared scope", { exact: false })).toBeVisible();
  await expect(
    base.getByText("Embedding model:", { exact: false }),
  ).toBeVisible();
  await base.getByRole("button", { name: `Edit ${name}`, exact: true }).click();
  await expect(page.getByLabel("Electricity", { exact: true })).toBeChecked();
  await page
    .getByLabel("Description", { exact: true })
    .fill("Updated synthetic scope");
  await expect(page.getByLabel("Use local AI only")).toBeChecked();
  if (testInfo.project.name.endsWith("dark"))
    await page.locator("html").evaluate((el) => el.classList.add("dark"));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("knowledge-edit.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Save knowledge base", exact: true })
    .click();
  await expect(
    base.getByText("Updated synthetic scope", { exact: true }),
  ).toBeVisible();
  await base
    .getByRole("button", { name: `Delete ${name}`, exact: true })
    .click();
  await base
    .getByRole("button", { name: "Confirm delete", exact: true })
    .click();
  await expect(base).toHaveCount(0);
  await page.getByRole("link", { name: "API tokens", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page.getByLabel("Local-only consumer", { exact: true }).check();
  await page.getByLabel("Ask knowledge bases", { exact: true }).check();
  await page.getByRole("button", { name: "Create token", exact: true }).click();
  await expect(page.getByLabel("New API token")).toHaveValue(/^dh_/);
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await expect(page.getByLabel("New API token")).toHaveCount(0);
  const token = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name, exact: true }) });
  await expect(
    token.getByText("Local-only consumer", { exact: false }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("api-tokens.png"),
    fullPage: true,
  });
  await token
    .getByRole("button", { name: `Revoke ${name}`, exact: true })
    .click();
  await token
    .getByRole("button", { name: "Confirm revoke", exact: true })
    .click();
  await expect(token.getByText("Revoked", { exact: true })).toBeVisible();
});
