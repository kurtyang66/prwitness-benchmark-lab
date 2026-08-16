import { defineConfig } from "@prwitness/config";

export default defineConfig({
  project: { name: "PRWitness synthetic benchmark", defaultBranch: "main" },
  app: {
    installCommand: "pnpm install --frozen-lockfile",
    buildCommand: "pnpm build",
    startCommand: "python3 -m http.server {port} --bind 127.0.0.1 --directory public",
    readyUrl: "http://127.0.0.1:{port}",
    baseRef: "origin/main",
  },
  playwright: {
    config: "playwright.config.mjs",
    grep: "@proof",
    timeout: 30_000,
    viewports: [{ name: "desktop", width: 1280, height: 720 }],
  },
  capture: {
    screenshots: true,
    video: false,
    trace: false,
    consoleErrors: true,
    pageErrors: true,
    failedRequests: true,
  },
  comparison: { threshold: 0.1, maxChangedPixelsPercent: 100 },
  output: { directory: ".prwitness" },
  github: { updateStickyComment: false, uploadArtifact: true },
  launch: {
    verticalVideo: false,
    landscapeVideo: false,
    gif: false,
    carousel: false,
    releaseNotes: false,
    socialDrafts: false,
  },
});
