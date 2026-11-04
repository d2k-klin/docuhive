import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/ui",
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  webServer: {
    command: "npm run dev -- --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 60000,
  },
  projects: [375, 768, 1280].flatMap((width) =>
    (["light", "dark"] as const).map((theme) => ({
      name: `${width}-${theme}`,
      use: { viewport: { width, height: 900 }, colorScheme: theme },
    })),
  ),
});
