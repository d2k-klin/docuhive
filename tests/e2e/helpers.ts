import { readFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";

export const CSRF = { "X-DocuHive-CSRF": "1" };

export async function signIn(page: Page, username: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic qa password 2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
}

export const stamp = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Uploads are deduplicated by content, and every project and rerun shares one archive:
// a trailing PDF comment makes each upload a new document without changing what it shows.
export const invoice = () => ({
  name: "invoice.pdf",
  mimeType: "application/pdf",
  buffer: Buffer.concat([
    readFileSync("tmp/qa/corpus/case-001.pdf"),
    Buffer.from(`\n%qa ${stamp()}\n`),
  ]),
});

// A unique "phone photo": a screenshot of a page that shows a unique line of text.
export async function photo(page: Page, label: string) {
  const sheet = await page.context().newPage();
  await sheet.setViewportSize({ width: 600, height: 800 });
  await sheet.setContent(
    `<body style="background:#fff;color:#000;font:32px sans-serif;padding:40px">Rechnung QA ${label}<br>${stamp()}<br>Amount: 84.20 EUR</body>`,
  );
  const buffer = await sheet.screenshot();
  await sheet.close();
  return { name: `${label}.png`, mimeType: "image/png", buffer };
}

// Generous: the stack shares a small Docker VM, and a broken file is retried before quarantine.
export const stored = { timeout: 150_000 };

// The review page shows one document at a time and loads its queue once. Other journeys and
// reruns leave suggestions behind, and the AI answers a few seconds after "Stored": dismiss
// everyone else's suggestions and reload until this document's own are on the page.
export async function openReviewOf(page: Page, href: string) {
  const id = href.split("/").pop();
  await expect(async () => {
    const queue = await (await page.request.get("/api/review/queue")).json();
    for (const group of queue.items)
      if (group.document.id !== id)
        await page.request.post(
          `/api/review/documents/${group.document.id}/reject-all`,
          { headers: { "X-DocuHive-CSRF": "1" } },
        );
    await page.goto("/review");
    await expect(page.locator(`a[href="${href}"]`)).toBeVisible({
      timeout: 3000,
    });
  }).toPass(stored);
  await expect(page.getByText("84.20").first()).toBeVisible();
}

export async function acceptAll(page: Page) {
  const accepted = page.waitForResponse(
    (response) => response.url().endsWith("/accept-all") && response.ok(),
  );
  await page.getByRole("button", { name: "Accept all" }).click();
  await accepted;
}

type Upload = { name: string; mimeType: string; buffer: Buffer };

/** Upload through the API as the signed-in user and wait until the document is stored. */
export async function store(
  page: Page,
  file: Upload,
  query: Record<string, string> = {},
  status = "stored",
): Promise<string> {
  const response = await page.request.post(
    `/api/upload?${new URLSearchParams(query)}`,
    { headers: CSRF, multipart: { files: file } },
  );
  expect(response.status()).toBe(202);
  const id = (await response.json()).document_id as string;
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/documents/${id}`)).json()).status,
      stored,
    )
    .toBe(status);
  return id;
}

/**
 * A unique born-digital PDF with the given text. Plain PDFs need neither the converter nor
 * OCR, which keeps the stack within a small Docker VM.
 */
export function letter(text: string) {
  const escape = (line: string) => line.replace(/([\\()])/g, "\\$1");
  const lines = `${text}\n${stamp()}`.split("\n").map(escape);
  const content = `BT /F1 12 Tf 50 780 Td 16 TL ${lines.map((l) => `(${l}) Tj T*`).join(" ")} ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${Buffer.byteLength(content, "latin1")} >>\nstream\n${content}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
  ];
  let body = "%PDF-1.4\n";
  const offsets = objects.map((object, index) => {
    const offset = Buffer.byteLength(body, "latin1");
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
    return offset;
  });
  const xref = Buffer.byteLength(body, "latin1");
  body += `xref\n0 6\n0000000000 65535 f \n${offsets
    .map((o) => `${String(o).padStart(10, "0")} 00000 n \n`)
    .join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return {
    name: "letter.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(body, "latin1"),
  };
}
