import { expect, test } from "@playwright/test";
import {
  acceptAll,
  invoice,
  openReviewOf,
  photo,
  signIn,
  stored,
} from "./helpers";

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

test("E2E-01 setup checklist @smoke @J3 @GUIDE-01 @GUIDE-02", async ({
  page,
}) => {
  await signIn(page, "alice");
  const checklist = page
    .getByRole("heading", { name: "Set up your archive" })
    .locator("xpath=ancestor::*[self::section or self::div][1]/..");
  await expect(page.getByText("Connect your storage (Done)")).toBeVisible();
  await expect(
    page.getByText(/required steps? left|Everything required is done/),
  ).toBeVisible();
  // Every step that is not done names its next action; the state comes from the server,
  // so it survives a reload.
  await page.reload();
  await expect(page.getByText("Back up your archive (Check)")).toBeVisible();
  await checklist.getByRole("link", { name: "Check backups" }).click();
  await expect(page).toHaveURL(/\/settings\/storage$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("E2E-02 upload and review @smoke @J1 @ING-01 @CLS-01 @DOC-02", async ({
  page,
}) => {
  test.setTimeout(300_000);
  await signIn(page, "alice");
  await page.goto("/upload");
  await page.getByLabel("Choose files to upload").setInputFiles(invoice());
  const row = page.getByRole("link", { name: /Stored/ });
  await expect(row).toBeVisible(stored);
  const href = (await row.getAttribute("href"))!;
  await openReviewOf(page, href);
  await acceptAll(page);
  await page.goto(href);
  await expect(page.getByText("Set manually").first()).toBeVisible();
  await expect(page.getByText("84.20").first()).toBeVisible();
});

test("E2E-03 upload metadata locks @J3 @DOC-08 @CLS-06", async ({ page }) => {
  test.setTimeout(300_000);
  await signIn(page, "alice");
  await page.goto("/upload");
  await page
    .getByRole("combobox", { name: "Category" })
    .selectOption("utilities/electricity");
  await page.getByLabel("Choose files to upload").setInputFiles(invoice());
  const row = page.getByRole("link", { name: /Stored/ });
  await expect(row).toBeVisible(stored);
  const href = (await row.getAttribute("href"))!;
  await page.goto(href);
  await expect(page.getByText("Set manually").first()).toBeVisible();
  // The AI classifies this file as plain "utilities"; the uploader's choice must survive it.
  await openReviewOf(page, href);
  await acceptAll(page);
  await page.goto(href);
  await expect(page.getByText("Electricity").first()).toBeVisible();
});

test("E2E-04 three page camera capture @J3 @CAP-01 @CAP-02", async ({
  page,
}) => {
  test.setTimeout(300_000);
  await signIn(page, "alice");
  await page.goto("/capture");
  await page
    .getByLabel("Choose capture files")
    .setInputFiles([
      await photo(page, "page-1"),
      await photo(page, "page-2"),
      await photo(page, "page-3"),
    ]);
  await expect(
    page
      .getByRole("list", { name: "Pages in upload order" })
      .getByRole("listitem"),
  ).toHaveCount(3);
  await page.getByLabel("Upload as one document").check();
  await page.getByRole("button", { name: "Upload document" }).click();
  const status = page.getByRole("region", { name: "Upload status" });
  await expect(status.getByRole("link")).toHaveCount(1, stored);
  await expect(status).not.toContainText("Processing…", stored);
  await expect(status).not.toContainText("needs attention");
  await status.getByRole("link").click();
  await expect(page.getByText("3 pages").first()).toBeVisible();
});

test("E2E-05 offline capture queue @J3 @CAP-01", async ({ page, context }) => {
  test.setTimeout(300_000);
  await signIn(page, "alice");
  await page.goto("/capture");
  await expect(
    page.getByRole("heading", { name: "Capture a document" }),
  ).toBeVisible();
  const shot = await photo(page, "offline");
  await context.setOffline(true);
  await page.getByLabel("Choose capture files").setInputFiles(shot);
  await page
    .getByRole("button", { name: "Save to upload when online" })
    .click();
  const status = page.getByRole("region", { name: "Upload status" });
  await expect(status).toContainText("Offline — queued: 1");
  await context.setOffline(false);
  await expect(status.getByRole("link")).toHaveCount(1, stored);
  await expect(status).not.toContainText("queued:");
  await expect(status).not.toContainText("Processing…", stored);
});
