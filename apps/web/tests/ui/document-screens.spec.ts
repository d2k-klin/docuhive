import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("upload, documents, detail, search, quarantine, trash, vocabulary and settings", async ({
  page,
}) => {
  test.skip(
    !process.env.DOCUHIVE_UI_TEST_PASSWORD,
    "Requires a synthetic account in the isolated test API with a worker.",
  );
  await page.goto("/login");
  await page
    .getByLabel("Username")
    .fill(process.env.DOCUHIVE_UI_TEST_USER || "oa_browser");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DOCUHIVE_UI_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  const title = `Synthetic receipt ${Date.now()}`;
  await page.getByRole("link", { name: "Upload", exact: true }).first().click();
  await page.getByLabel("Category").selectOption("utilities/electricity");
  await page.getByLabel("Choose files to upload").setInputFiles({
    name: `${title}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`${title} from Stadtwerke Muster, total 84.20 EUR`),
  });
  await expect(page.getByText("Stored", { exact: true })).toBeVisible({
    timeout: 60_000,
  });

  await page.getByRole("link", { name: title }).click();
  await expect(
    page.getByRole("heading", { name: title, level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Sender").fill("Stadtwerke Muster");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("locked against the AI")).toBeVisible();

  await page.goto(`/search?q=${encodeURIComponent("Stadtwerke")}`);
  await expect(page.getByRole("link", { name: title })).toBeVisible();

  for (const [path, heading] of [
    ["/documents", "Documents"],
    ["/quarantine", "Quarantine"],
    ["/trash", "Trash"],
    ["/vocabulary", "Vocabulary"],
    ["/settings/account", "Settings"],
    ["/", "DocuHive"],
  ]) {
    await page.goto(path);
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
});
