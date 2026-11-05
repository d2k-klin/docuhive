import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const account = {
  id: 7,
  provider: "imap",
  address: "archive@example.org",
  display_name: null,
  status: "active",
  last_sync_at: null,
};
const connection = {
  credentials_ready: true,
  sync_every_min: 15,
  oauth_redirects: {
    google: "http://localhost:3000/api/sources/oauth/google/callback",
    microsoft: "http://localhost:3000/api/sources/oauth/microsoft/callback",
  },
};

async function signIn(page: Page) {
  await page.goto("/login?next=%2Fsources");
  await page
    .getByLabel("Username")
    .fill(process.env.DOCUHIVE_UI_TEST_USER || "oa_browser");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DOCUHIVE_UI_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test.beforeEach(async ({ page }) => {
  test.skip(
    !process.env.DOCUHIVE_UI_TEST_PASSWORD,
    "Requires a synthetic account in the isolated test API.",
  );
  await signIn(page);
});

test("choose a provider, recover from a failed login and import attachments", async ({
  page,
}, testInfo) => {
  let saved = false;
  let attempts = 0;
  let imported = false;
  await page.route("**/api/sources/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/sources/accounts" && request.method() === "POST") {
      expect(request.postDataJSON()).toMatchObject({
        provider: "imap",
        host: "imap.gmail.com",
        address: "archive@gmail.com",
        folders: ["INBOX"],
      });
      attempts++;
      if (attempts === 1)
        return route.fulfill({
          status: 400,
          json: {
            error: {
              code: "imap_login_failed",
              message:
                "The mail server refused the login. Check your app password.",
            },
          },
        });
      saved = true;
      return route.fulfill({
        json: { ...account, address: "archive@gmail.com" },
      });
    }
    if (path.endsWith("/backfills") && request.method() === "POST") {
      const range = request.postDataJSON();
      expect(range.date_from < range.date_to).toBe(true);
      expect(range.date_from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      imported = true;
      return route.fulfill({ json: { id: 1 } });
    }
    return route.fulfill({
      json: path.endsWith("/accounts")
        ? {
            items: saved ? [{ ...account, address: "archive@gmail.com" }] : [],
            triage_local: true,
            oauth: { google: false, microsoft: false },
            connection,
          }
        : { items: [] },
    });
  });
  await page.goto("/sources");
  if (testInfo.project.name.endsWith("dark"))
    await page.locator("html").evaluate((el) => el.classList.add("dark"));
  await expect(
    page.getByRole("button", { name: "Gmail Google & Google Workspace" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("sources-providers.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Gmail Google & Google Workspace" })
    .click();
  await page
    .getByLabel("Email address", { exact: true })
    .fill("archive@gmail.com");
  await page.getByLabel(/^App password/).fill("synthetic-app-password");
  await page
    .getByRole("button", { name: "Connect mailbox", exact: true })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /refused the login|Mail credential storage/ }),
  ).toContainText("refused the login");
  await expect(page.getByLabel("Email address", { exact: true })).toHaveValue(
    "archive@gmail.com",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("sources-connect.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Connect mailbox", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Import existing attachments" }),
  ).toBeVisible();
  expect(imported).toBe(false);
  await page.getByRole("button", { name: "Last year", exact: true }).click();
  await page
    .getByRole("button", { name: "Import attachments", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "History import started",
  );
  expect(imported).toBe(true);
});

test("provider sign-in is primary and missing Outlook setup has usable instructions", async ({
  page,
}, testInfo) => {
  let enabled = false;
  await page.route("**/api/sources/**", (route) =>
    route.fulfill({
      json: route.request().url().includes("/accounts")
        ? {
            items: [],
            triage_local: true,
            oauth: { google: true, microsoft: enabled },
            connection,
          }
        : { items: [] },
    }),
  );
  await page.goto("/sources?connect=gmail");
  await expect(
    page.getByRole("link", { name: "Continue with Google" }),
  ).toHaveAttribute("href", "/api/sources/oauth/google/start");
  await expect(page.getByLabel(/^App password/)).toHaveCount(0);
  await page.getByRole("button", { name: "Change provider" }).click();
  await page
    .getByRole("button", { name: "Outlook Microsoft 365, Hotmail & Live" })
    .click();
  await page
    .getByText("Set up Microsoft sign-in on this server", { exact: true })
    .click();
  await expect(
    page.getByText(connection.oauth_redirects.microsoft, { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  if (testInfo.project.name.endsWith("dark"))
    await page.locator("html").evaluate((el) => el.classList.add("dark"));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("sources-outlook-setup.png"),
    fullPage: true,
  });
  enabled = true;
  await page.reload();
  // Query links also support the setup wizard and reconnect entry points.
  await page.goto("/sources?connect=outlook");
  await expect(
    page.getByRole("link", { name: "Continue with Microsoft" }),
  ).toHaveAttribute("href", "/api/sources/oauth/microsoft/start");
});

test("custom mailbox settings and missing encryption key are handled before connecting", async ({
  page,
}) => {
  await page.route("**/api/sources/**", (route) =>
    route.fulfill({
      json: route.request().url().includes("/accounts")
        ? {
            items: [],
            triage_local: true,
            oauth: { google: false, microsoft: false },
            connection: { ...connection, credentials_ready: false },
          }
        : { items: [] },
    }),
  );
  await page.goto("/sources?connect=imap");
  await page
    .getByLabel("Email address", { exact: true })
    .fill("archive@custom.example");
  await page
    .getByLabel("Mail server", { exact: true })
    .fill("mail.custom.example");
  await expect(page.getByLabel("Mail server", { exact: true })).toBeVisible();
  await page.getByLabel(/^Username/).fill("archive-login");
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /refused the login|Mail credential storage/ }),
  ).toContainText("Mail credential storage needs setting up first");
  await expect(
    page.getByRole("button", { name: "Connect mailbox", exact: true }),
  ).toBeDisabled();
});

test("returning from provider sign-in offers history without starting it automatically", async ({
  page,
}) => {
  await page.route("**/api/sources/**", async (route) => {
    expect(route.request().method()).toBe("GET");
    return route.fulfill({
      json: route.request().url().includes("/accounts")
        ? {
            items: [{ ...account, provider: "gmail" }],
            triage_local: true,
            oauth: { google: true, microsoft: true },
            connection,
          }
        : { items: [] },
    });
  });
  await page.goto("/sources?connected=7");
  await expect(
    page.getByRole("heading", { name: "Import existing attachments" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Mailbox connected");
  await page.getByRole("button", { name: "Skip for now", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Import existing attachments" }),
  ).toHaveCount(0);
  await expect(page.getByText(account.address, { exact: true })).toBeVisible();
});
