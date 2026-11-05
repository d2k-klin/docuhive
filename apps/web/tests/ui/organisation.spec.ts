import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const id = "01JCAAAAAAAAAAAAAAAAAAAAAA";
const second = "01JCBBBBBBBBBBBBBBBBBBBBBB";
const third = "01JCCCCCCCCCCCCCCCCCCCCCCC";
const categories = [
  {
    id: "finance",
    label: "Finance",
    description: "",
    restricted: false,
    enabled: true,
  },
  {
    id: "finance/banking",
    label: "Banking",
    description: "Bank statements",
    restricted: false,
    enabled: true,
  },
  {
    id: "finance/tax",
    label: "Tax",
    description: "Tax documents",
    restricted: false,
    enabled: true,
  },
  {
    id: "health",
    label: "Health",
    description: "Medical records",
    restricted: true,
    enabled: true,
  },
  {
    id: "other",
    label: "Other",
    description: "",
    restricted: false,
    enabled: true,
  },
];
const taxonomy = {
  categories,
  document_types: [
    { id: "bank-statement", label: "Bank statement", facts: [] },
  ],
  tags: [],
  languages: ["en"],
  version: 1,
  preset_ids: categories.map((c) => c.id),
};
const fixtureDocument = {
  id,
  title: "October bank statement",
  category: "finance/banking",
  document_date: "2026-10-10",
  added_at: "2026-11-01T10:00:00Z",
  document_type: "bank-statement",
  correspondent: "Example bank",
  tags: [],
};

async function verify(
  page: Page,
  testInfo: { project: { name: string }; outputPath: (name: string) => string },
  screenshot: string,
) {
  if (testInfo.project.name.endsWith("dark"))
    await page.locator("html").evaluate((el) => el.classList.add("dark"));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath(screenshot),
    fullPage: true,
  });
}

test.beforeEach(async ({ page }) => {
  test.skip(
    !process.env.DOCUHIVE_UI_TEST_PASSWORD,
    "Requires a synthetic account in an isolated test API.",
  );
  await page.goto("/login?next=%2Fsources");
  await page
    .getByLabel("Username")
    .fill(process.env.DOCUHIVE_UI_TEST_USER || "oa_browser");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DOCUHIVE_UI_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
});

test("choose predefined categories and persist a custom category", async ({
  page,
}, testInfo) => {
  const data = structuredClone(taxonomy);
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/taxonomy/categories" && request.method() === "PUT") {
      const selected = request.postDataJSON().enabled_ids as string[];
      expect(selected).toEqual(
        expect.arrayContaining(["finance", "finance/banking", "other"]),
      );
      expect(selected).not.toContain("health");
      data.categories = data.categories.map((c) => ({
        ...c,
        enabled: selected.includes(c.id),
      }));
      return route.fulfill({ json: data });
    }
    if (path === "/api/taxonomy/categories" && request.method() === "POST") {
      expect(request.postDataJSON()).toMatchObject({
        label: "Home business",
        parent_id: "finance",
        restricted: true,
      });
      data.categories.push({
        id: "finance/home-business",
        label: "Home business",
        description: "Business invoices",
        restricted: true,
        enabled: true,
      });
      return route.fulfill({ json: data });
    }
    return route.fulfill({ json: path === "/api/taxonomy" ? data : [] });
  });
  await page.goto("/vocabulary");
  await page.getByRole("button", { name: "Clear optional categories" }).click();
  await page
    .getByRole("checkbox", { name: "Use Finance", exact: true })
    .check();
  await expect(
    page.getByRole("checkbox", { name: "Use Banking", exact: true }),
  ).toBeChecked();
  await page.getByRole("button", { name: "Save category choices" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Category choices saved",
  );
  await page.getByRole("button", { name: "Add category", exact: true }).click();
  await page.getByLabel("Category name", { exact: true }).fill("Home business");
  await page
    .getByRole("combobox", { name: "Parent category", exact: true })
    .selectOption("finance");
  await page.getByLabel(/What belongs here/).fill("Business invoices");
  await page
    .getByRole("checkbox", {
      name: "Keep documents in this category on local AI only",
    })
    .check();
  await page
    .getByRole("button", { name: "Create category", exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "Use Home business", exact: true }),
  ).toBeChecked();
  await page.reload();
  await expect(
    page.getByRole("checkbox", { name: "Use Health", exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "Use Home business", exact: true }),
  ).toBeChecked();
  await verify(page, testInfo, "categories.png");
});

test("group Finance by month or quarter and save the current date range", async ({
  page,
}, testInfo) => {
  await page.clock.install({ time: new Date(2026, 10, 5, 12) });
  let documentUrl = "";
  let saved = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/taxonomy")
      return route.fulfill({ json: taxonomy });
    if (url.pathname === "/api/documents") {
      documentUrl = url.search;
      const items = [
        fixtureDocument,
        {
          ...fixtureDocument,
          id: second,
          title: "Undated tax receipt",
          category: "finance/tax",
          document_date: null,
          added_at: "2026-10-31T23:59:00Z",
        },
        {
          ...fixtureDocument,
          id: third,
          title: "September bank statement",
          document_date: "2026-09-30",
        },
      ].filter((doc) => {
        const date = doc.document_date || doc.added_at.slice(0, 10);
        const category = url.searchParams.get("category");
        return (
          (!category ||
            doc.category === category ||
            doc.category.startsWith(`${category}/`)) &&
          (!url.searchParams.get("date_from") ||
            date >= url.searchParams.get("date_from")!) &&
          (!url.searchParams.get("date_to") ||
            date <= url.searchParams.get("date_to")!)
        );
      });
      return route.fulfill({
        json: { items, total: items.length, next_offset: null },
      });
    }
    if (url.pathname === "/api/ai/documents/status")
      return route.fulfill({
        json: {
          items: [id, second, third].map((document_id) => ({
            document_id,
            status: "categorized",
            stage: null,
            category:
              document_id === second ? "finance/tax" : "finance/banking",
            category_label: document_id === second ? "Tax" : "Banking",
            suggested_category: null,
            ai_run_id: 21,
          })),
        },
      });
    if (url.pathname === "/api/views" && request.method() === "POST") {
      expect(request.postDataJSON()).toMatchObject({
        name: "Finance October",
        pinned: true,
        filters: {
          categories: ["finance"],
          date_from: "2026-10-01",
          date_to: "2026-10-31",
        },
      });
      saved = true;
      return route.fulfill({ json: { id: 9 } });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto("/documents");
  await page
    .getByRole("combobox", { name: "Category", exact: true })
    .selectOption("finance");
  await page.getByRole("button", { name: "Last month", exact: true }).click();
  await expect.poll(() => documentUrl).toContain("date_from=2026-10-01");
  expect(documentUrl).toContain("date_to=2026-10-31");
  expect(documentUrl).toContain("category=finance");
  await expect(page.getByText("Upload date", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Save this view" }).click();
  await page.getByLabel("View name", { exact: true }).fill("Finance October");
  await page.getByRole("button", { name: "Save view", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("View saved");
  expect(saved).toBe(true);
  await page.getByRole("button", { name: "Last quarter", exact: true }).click();
  await expect.poll(() => documentUrl).toContain("date_from=2026-07-01");
  expect(documentUrl).toContain("date_to=2026-09-30");
  await verify(page, testInfo, "finance-group.png");
});

test("AI status follows the queue and a category becomes applied after acceptance", async ({
  page,
}, testInfo) => {
  let phase: "queued" | "running" | "needs_review" = "queued";
  let accepted = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/taxonomy") return route.fulfill({ json: taxonomy });
    if (path === `/api/documents/${id}`)
      return route.fulfill({
        json: {
          ...fixtureDocument,
          category: accepted ? "finance/banking" : null,
          owner_id: 1,
          shared: false,
          status: "stored",
          mime: "application/pdf",
          pages: 1,
          language: "en",
          files: [],
          facts: {},
          manual_fields: [],
          source: { kind: "upload", original_filename: "statement.pdf" },
          provenance: {},
          quarantine_reason: null,
        },
      });
    if (path === "/api/ai/documents/status") {
      const status = accepted ? "categorized" : phase;
      return route.fulfill({
        json: {
          items: [
            {
              document_id: id,
              status,
              stage: "ai.classify",
              category: accepted ? "finance/banking" : null,
              category_label: accepted ? "Banking" : null,
              suggested_category: accepted ? null : "Banking",
              ai_run_id: phase === "needs_review" ? 21 : null,
            },
          ],
        },
      });
    }
    if (path === "/api/review/queue")
      return route.fulfill({
        json: {
          items:
            !accepted && phase === "needs_review"
              ? [
                  {
                    document: { id, can_resolve: true },
                    items: [
                      {
                        id: 11,
                        kind: "field",
                        field: "category",
                        suggested: { value: "finance/banking" },
                        confidence: 0.95,
                        reason: null,
                      },
                    ],
                  },
                ]
              : [],
        },
      });
    if (path === "/api/review/items/11/accept") {
      accepted = true;
      return route.fulfill({ json: { applied: ["category"] } });
    }
    return route.fulfill({
      json:
        path.endsWith("/history") || path.endsWith("setup-status")
          ? []
          : { items: [] },
    });
  });
  await page.goto(`/documents/${id}`);
  const panel = page.locator("section").filter({
    has: page.getByRole("heading", { name: "AI analysis", exact: true }),
  });
  await expect(panel.getByText("AI queued", { exact: true })).toBeVisible();
  phase = "running";
  await expect(panel.getByText("Categorising…", { exact: true })).toBeVisible({
    timeout: 10000,
  });
  phase = "needs_review";
  await expect(
    panel.getByText("Completed · needs review", { exact: true }),
  ).toBeVisible({ timeout: 10000 });
  await expect(panel.getByText(/Suggested category: Banking/)).toBeVisible();
  await panel
    .getByRole("button", { name: "Accept Category", exact: true })
    .click();
  await expect(panel.getByText("Categorized", { exact: true })).toBeVisible();
  await expect(panel.getByText(/Categorized as Banking/)).toBeVisible();
  await verify(page, testInfo, "ai-complete.png");
});
