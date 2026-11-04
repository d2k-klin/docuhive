import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: { id: 1, username: "synthetic", role: "member" } }),
  );
  await page.route("**/api/upload?**", (route) =>
    route.fulfill({
      status: 202,
      json: { document_id: "synthetic", status: "staged" },
    }),
  );
});

test("capture layout and accessible page ordering", async ({ page }) => {
  await page.goto("/capture");
  await page.locator('input[aria-label="Choose capture files"]').setInputFiles([
    {
      name: "first.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-synthetic-first"),
    },
    {
      name: "second.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-synthetic-second"),
    },
  ]);
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await page.getByRole("button", { name: "Move page 2 earlier" }).click();
  await expect(page.getByRole("listitem").first()).toContainText("second.pdf");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("IndexedDB survives reload and serialises concurrent queue senders", async ({
  page,
}) => {
  await page.goto("/capture");
  await expect(
    page.getByRole("heading", { name: "Capture a document" }),
  ).toBeVisible();
  const result = await page.evaluate(async () => {
    // Load the exact module used by both the page and service worker.
    const modulePath = "/capture-queue.js";
    const queue = await import(/* webpackIgnore: true */ modulePath);
    await queue.save({
      id: "persistent",
      ownerId: 1,
      blobs: [
        new File(["%PDF-synthetic"], "letter.pdf", { type: "application/pdf" }),
      ],
      combine: false,
      createdAt: Date.now(),
      attempts: 0,
      nextAttempt: 0,
    });
    return (await queue.entries()).length;
  });
  expect(result).toBe(1);
  let uploads = 0;
  await page.route("**/api/upload?**", async (route) => {
    uploads++;
    await new Promise((resolve) => setTimeout(resolve, 50));
    await route.fulfill({
      status: 503,
      json: { error: { code: "intake_unavailable" } },
    });
  });
  await page.reload();
  await expect(page.getByText("letter.pdf", { exact: true })).toBeVisible();
  await page.evaluate(async () => {
    const modulePath = "/capture-queue.js";
    const queue = await import(/* webpackIgnore: true */ modulePath);
    await Promise.all([queue.flush(), queue.flush()]);
  });
  expect(uploads).toBe(1);
  await expect
    .poll(() =>
      page.evaluate(async () => {
        const modulePath = "/capture-queue.js";
        const queue = await import(/* webpackIgnore: true */ modulePath);
        return (await queue.entries())[0]?.attempts;
      }),
    )
    .toBe(1);
  const queued = await page.evaluate(async () => {
    const modulePath = "/capture-queue.js";
    const queue = await import(/* webpackIgnore: true */ modulePath);
    return queue.entries();
  });
  expect(queued).toHaveLength(1);
  expect(queued[0].attempts).toBe(1);
});

test("capture reopens offline and sends its durable queue after reconnecting", async ({
  page,
  context,
}) => {
  await page.goto("/capture");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("capture-owner")))
    .toBe("1");
  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Capture a document" }),
  ).toBeVisible();
  await page.locator('input[aria-label="Choose capture files"]').setInputFiles({
    name: "offline.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-synthetic-offline"),
  });
  await page
    .getByRole("button", { name: "Save to upload when online" })
    .click();
  await expect(page.getByText(/Offline — queued: 1/)).toBeVisible();
  await page.reload();
  await expect(page.getByText("offline.pdf", { exact: true })).toBeVisible();
  await context.setOffline(false);
  await expect(
    page.getByText("Processing… Your file has been accepted."),
  ).toBeVisible();
  await expect(page.getByText("offline.pdf", { exact: true })).toHaveCount(0);
});

test("photo preparation, rotation and combining preserve page order", async ({
  page,
}, info) => {
  let uploaded: { names: string[]; combine: string | null } | undefined;
  await page.route("**/api/upload?**", async (route) => {
    const request = route.request();
    const form = await new Request(request.url(), {
      method: "POST",
      headers: { "content-type": request.headers()["content-type"] },
      body: new Uint8Array(request.postDataBuffer()!),
    }).formData();
    uploaded = {
      names: form.getAll("files").map((file) => (file as File).name),
      combine: new URL(request.url()).searchParams.get("combine"),
    };
    await route.fulfill({
      status: 202,
      json: { document_id: "photos", status: "staged" },
    });
  });
  await page.goto("/capture");
  const image = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 3200;
    canvas.height = 2400;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "white";
    context.fillRect(0, 0, 3200, 2400);
    context.fillStyle = "black";
    context.font = "100px sans-serif";
    context.fillText("Synthetic letter page", 200, 400);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.locator('input[aria-label="Camera photos"]').setInputFiles([
    {
      name: "first.png",
      mimeType: "image/png",
      buffer: Buffer.from(image, "base64"),
    },
    {
      name: "second.png",
      mimeType: "image/png",
      buffer: Buffer.from(image, "base64"),
    },
  ]);
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await page.getByRole("button", { name: "Rotate page 1" }).click();
  await page.getByRole("button", { name: "Move page 2 earlier" }).click();
  const dimensions = await page
    .locator('img[alt="Page 2 preview"]')
    .evaluate(async (image) => {
      await (image as HTMLImageElement).decode();
      return [
        (image as HTMLImageElement).naturalWidth,
        (image as HTMLImageElement).naturalHeight,
      ];
    });
  expect(dimensions).toEqual([1800, 2400]);
  await page.screenshot({
    path: info.outputPath("capture.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Upload document", exact: true })
    .click();
  await expect
    .poll(() => uploaded)
    .toEqual({ names: ["second.jpg", "first.jpg"], combine: "true" });
});

test("another account stays queued and rejected files retain their bytes", async ({
  page,
}) => {
  let uploads = 0;
  await page.route("**/api/upload?**", async (route) => {
    uploads++;
    await route.fulfill({
      status: 413,
      json: { error: { code: "too_large" } },
    });
  });
  await page.goto("/capture");
  await page.evaluate(async () => {
    const modulePath = "/capture-queue.js";
    const queue = await import(/* webpackIgnore: true */ modulePath);
    for (const ownerId of [2, 1])
      await queue.save({
        id: `owner-${ownerId}`,
        ownerId,
        blobs: [new File(["kept bytes"], "letter.pdf")],
        combine: false,
        createdAt: Date.now(),
        attempts: 0,
        nextAttempt: 0,
      });
    await queue.flush();
  });
  await expect
    .poll(() =>
      page.evaluate(async () => {
        const modulePath = "/capture-queue.js";
        const queue = await import(/* webpackIgnore: true */ modulePath);
        return (await queue.entries()).map(
          (item: {
            ownerId: number;
            error?: string;
            attempts: number;
            blobs: File[];
          }) => ({
            ownerId: item.ownerId,
            error: item.error,
            attempts: item.attempts,
            bytes: item.blobs[0].size,
          }),
        );
      }),
    )
    .toEqual([
      { ownerId: 1, error: "too_large", attempts: 1, bytes: 10 },
      { ownerId: 2, error: undefined, attempts: 0, bytes: 10 },
    ]);
  expect(uploads).toBe(1);
});
