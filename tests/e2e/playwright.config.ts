import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  retries: 0,
  workers: 1,
  forbidOnly: !!process.env.CI,
  timeout: 30_000,
  outputDir: "../../tmp/qa/browser-results",
  reporter: [
    ["list"],
    ["json", { outputFile: "../../tmp/qa/playwright.json" }],
  ],
  use: {
    baseURL: process.env.DOCUHIVE_QA_WEB_URL ?? "https://127.0.0.1:53100",
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [375, 768, 1280].flatMap((width) =>
    (["light", "dark"] as const).map((theme) => ({
      name: `${width}-${theme}`,
      use: {
        viewport: { width, height: 900 },
        colorScheme: theme,
        isMobile: width === 375,
        hasTouch: width === 375,
      },
    })),
  ),
});
