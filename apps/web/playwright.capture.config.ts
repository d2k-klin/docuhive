import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

// Offline hydration needs production assets; next dev's on-demand chunks are not cacheable.
export default defineConfig({
  ...base,
  testDir: "tests/capture",
  use: { ...base.use, baseURL: "http://127.0.0.1:3135" },
  webServer: {
    command: "npm run start -- --port 3135",
    url: "http://127.0.0.1:3135/capture",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
