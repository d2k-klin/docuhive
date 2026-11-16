import { readFileSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";
import { CSRF, signIn, stamp, store } from "./helpers";

// One journey per example plugin, on the data the QA seed made for alice. Only the 1280 light
// project runs them: the layouts are covered at every size by ui-consistency.spec.ts.
test.beforeEach(({}, info) => {
  test.skip(info.project.name !== "1280-light", "journeys run once");
  test.setTimeout(240_000); // storing and printing share a small Docker VM, as in helpers.stored
});

/** Text on screen: tables exist twice (cards on phones, a table on wider screens). */
const seen = (page: Page, text: string | RegExp) =>
  page.getByText(text).locator("visible=true").first();

/** Answer the page's confirm dialog, then press a button. */
async function press(page: Page, name: string) {
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name, exact: true }).click();
}

test("PLG-01 tax: a draft invoice is issued with a number and locked @plugins", async ({
  page,
}) => {
  await signIn(page, "alice");
  const form = await (
    await page.request.get("/api/plugin-pages/steuer-de/invoices/blocks/1")
  ).json();
  const made = await page.request.post(
    "/api/plugin-pages/steuer-de/invoices/actions/save_draft",
    {
      headers: CSRF,
      data: {
        customer_id: form.options.customer_id[0].value,
        service_to: "2026-03-31",
        lines: [
          {
            description: `Beratung ${stamp()}`,
            quantity: "8",
            unit: "HUR",
            unit_price: "95.00",
            vat_code: "sale_19",
          },
        ],
      },
    },
  );
  expect(made.status()).toBe(200);
  await page.goto(`/plugins/steuer-de/${(await made.json()).goto}`);
  await expect(seen(page, "Draft")).toBeVisible();
  await press(page, "Issue");
  await expect(seen(page, /^RE-\d{4}-\d{4}$/)).toBeVisible({
    timeout: 120_000,
  });
  await expect(seen(page, "€904.40")).toBeVisible();
  await page
    .getByRole("link", { name: "Open" })
    .locator("visible=true")
    .first()
    .click();
  await expect(page.getByText("Locked", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Move to trash" }),
  ).toBeDisabled();
});

test("PLG-02 tax: a booking without a document shows in the quarter @plugins", async ({
  page,
}) => {
  await signIn(page, "alice");
  await page.goto("/plugins/steuer-de/entries");
  await expect(seen(page, "Kunde Eins")).toBeVisible();
  await page.goto("/plugins/steuer-de/periods");
  await expect(page.getByRole("link", { name: "2026-Q1" })).toBeVisible();
});

test("PLG-03 bank: a statement becomes payments @plugins", async ({ page }) => {
  await signIn(page, "alice");
  const xml = readFileSync("tests/e2e/fixtures/camt-march.xml", "utf8").replace(
    "</Document>",
    `<!-- qa ${stamp()} --></Document>`,
  );
  await store(page, {
    name: "march.xml",
    mimeType: "application/xml",
    buffer: Buffer.from(xml),
  });
  await expect(async () => {
    await page.goto("/plugins/bank/transactions");
    await expect(seen(page, "1,500.00")).toBeVisible({
      timeout: 3000,
    });
  }).toPass({ timeout: 120_000 });
});

test("PLG-04 inventory: an item added by hand, with its warranty @plugins", async ({
  page,
}) => {
  await signIn(page, "alice");
  const name = `Bohrmaschine ${stamp()}`;
  await page.goto("/plugins/inventar/items");
  const form = page
    .locator("form")
    .filter({ has: page.getByLabel("Bought on") });
  await form.getByLabel("Name (required)").fill(name);
  await form.getByLabel("Bought on").fill("2026-02-01");
  await form.getByLabel("Price").fill("129.00");
  await form.getByRole("button", { name: "Add" }).click();
  await expect(seen(page, name)).toBeVisible();
  await expect(seen(page, "Assumed")).toBeVisible();
});

test("PLG-05 landlord: a flat is added and a draft statement computed @plugins", async ({
  page,
}) => {
  await signIn(page, "alice");
  await page.goto("/plugins/vermieter-de/properties");
  await expect(seen(page, "Mieter Eins")).toBeVisible();
  const tenancies = await (
    await page.request.get("/api/plugin-pages/vermieter-de/statements/blocks/0")
  ).json();
  const tenancy = tenancies.options.tenancy[0].value;
  await page.goto(
    `/plugins/vermieter-de/statements?tenancy=${tenancy}&year=2025`,
  );
  await expect(seen(page, "Advance payments")).toBeVisible();
  await expect(seen(page, "-€1,200.00")).toBeVisible();
});

test("PLG-06 contracts and school: pages and dashboard cards @plugins", async ({
  page,
}) => {
  await signIn(page, "alice");
  await page.goto("/plugins/vertraege/contracts");
  await expect(seen(page, "No contracts yet.")).toBeVisible();
  await page.goto("/plugins/schule/letters");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.goto("/");
  await expect(page.getByText("Contracts per month")).toBeVisible();
  await expect(page.getByText("Value of your things")).toBeVisible();
});

test("PLG-07 plugin API refuses another user's tenancy @plugins @AUTH-03", async ({
  page,
}) => {
  await signIn(page, "bob");
  const response = await page.request.post(
    "/api/plugin-pages/vermieter-de/properties/actions/save_unit",
    { headers: CSRF, data: { property: "1", name: "X", area: "10" } },
  );
  expect(response.status()).toBe(422);
});
