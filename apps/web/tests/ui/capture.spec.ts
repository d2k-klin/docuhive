import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: { id: 1, username: "synthetic", role: "member" } }));
  await page.route("**/api/upload?**", route => route.fulfill({ status: 202, json: { document_id: "synthetic", status: "staged" } }));
});

test("capture layout and accessible page ordering", async ({ page }) => {
  await page.goto("/capture");
  await page.locator('input[aria-label="Choose capture files"]').setInputFiles([
    { name: "first.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-synthetic-first") },
    { name: "second.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-synthetic-second") },
  ]);
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await page.getByRole("button", { name: "Move page 2 earlier" }).click();
  await expect(page.getByRole("listitem").first()).toContainText("second.pdf");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("IndexedDB survives reload and serialises concurrent queue senders", async ({ page }) => {
  await page.goto("/capture");
  await expect(page.getByRole("heading", { name: "Capture a document" })).toBeVisible();
  const result = await page.evaluate(async () => {
    // Load the exact module used by both the page and service worker.
    const queue = await import(/* webpackIgnore: true */ "/capture-queue.js");
    await queue.save({ id: "persistent", ownerId: 1, blobs: [new File(["%PDF-synthetic"], "letter.pdf", { type: "application/pdf" })], combine: false, createdAt: Date.now(), attempts: 0, nextAttempt: 0 });
    return (await queue.entries()).length;
  });
  expect(result).toBe(1);
  let uploads = 0;
  await page.route("**/api/upload?**", async route => {
    uploads++;
    await new Promise(resolve => setTimeout(resolve, 50));
    await route.fulfill({ status: 503, json: { error: { code: "intake_unavailable" } } });
  });
  await page.reload();
  await expect(page.getByText("letter.pdf", { exact: true })).toBeVisible();
  await page.evaluate(async () => {
    const queue = await import(/* webpackIgnore: true */ "/capture-queue.js");
    await Promise.all([queue.flush(), queue.flush()]);
  });
  expect(uploads).toBe(1);
  const queued = await page.evaluate(async () => {
    const queue = await import(/* webpackIgnore: true */ "/capture-queue.js");
    return queue.entries();
  });
  expect(queued).toHaveLength(1);
  expect(queued[0].attempts).toBe(1);
});
