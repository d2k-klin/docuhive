import { expect, test } from "@playwright/test";

test("Login, member boundary and logout @smoke @AUTH-01 @AUTH-04", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("bob");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic qa password 2026");
  const login = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  const response = await login;
  expect(response.status()).toBe(204);
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  expect((await page.request.get("/api/users")).status()).toBe(403);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});

test("E2E-01 setup wizard @smoke @J3 @GUIDE-01 @GUIDE-02", async ({ page }) => {
  test.fixme(true, "OA-M5 wizard pending: docs/Developer-QA/bugs.md#qa-002");
  await page.goto("/setup");
  await expect(page.getByRole("heading", { name: "Storage" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "AI provider" }),
  ).toBeVisible();
});

test("E2E-02 upload and review @smoke @J1 @ING-01 @CLS-01 @DOC-02", async ({
  page,
}) => {
  test.fixme(
    true,
    "OA-M3/M5 archive pending: docs/Developer-QA/bugs.md#qa-001",
  );
  await page.goto("/documents");
  await page.getByRole("button", { name: "Upload" }).click();
  await page
    .locator("input[type=file]")
    .setInputFiles("tmp/qa/corpus/case-001.pdf");
  await expect(page.getByText("Stored", { exact: true })).toBeVisible();
  await page.goto("/review");
  await expect(page.getByText("84.20")).toBeVisible();
  await page
    .getByRole("button", { name: "Accept", exact: true })
    .first()
    .click();
  await expect(page.getByText("You", { exact: true }).first()).toBeVisible();
});

test("E2E-03 upload metadata locks @J3 @DOC-08 @CLS-06", async ({ page }) => {
  test.fixme(
    true,
    "OA-M5 upload metadata pending: docs/Developer-QA/bugs.md#qa-001",
  );
  await page.goto("/upload");
  await page
    .locator("input[type=file]")
    .setInputFiles("tmp/qa/corpus/case-001.pdf");
  await page
    .getByRole("combobox", { name: "Category" })
    .selectOption("utilities/electricity");
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("You", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Electricity", { exact: true })).toBeVisible();
});

test("E2E-04 three page camera capture @J3 @CAP-01 @CAP-02", async ({
  page,
}) => {
  test.fixme(true, "OA-M6 capture pending: docs/Developer-QA/bugs.md#qa-003");
  await page.goto("/capture");
  await page
    .locator("input[type=file]")
    .setInputFiles([1, 2, 3].map((n) => `tmp/qa/corpus/case-00${n}-phone.jpg`));
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText("3 pages", { exact: true })).toBeVisible();
});

test("E2E-05 offline capture queue @J3 @CAP-01", async ({ page, context }) => {
  test.fixme(
    true,
    "OA-M6 offline queue pending: docs/Developer-QA/bugs.md#qa-003",
  );
  await page.goto("/capture");
  await context.setOffline(true);
  await page
    .locator("input[type=file]")
    .setInputFiles("tmp/qa/corpus/case-001-phone.jpg");
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  await context.setOffline(false);
  await expect(page.getByText("Stored", { exact: true })).toBeVisible();
});
