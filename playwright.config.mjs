import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  use: {
    baseURL: process.env.PRWITNESS_BASE_URL,
    headless: true,
    video: "off",
    trace: "off",
  },
});
