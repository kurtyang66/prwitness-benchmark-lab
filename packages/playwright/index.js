import { mkdir, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { expect, test as base } from "@playwright/test";

const selectorVariable = "PRWITNESS_FLOW_SELECTOR";

function safeSegment(value) {
  const segment = String(value)
    .normalize("NFKC")
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
  return segment || "flow";
}

function flowId(testInfo) {
  return safeSegment(
    `${testInfo.title}-${testInfo.project.name || "default"}-${testInfo.testId.slice(0, 8)}`,
  );
}

function selected(testInfo) {
  const selector = process.env[selectorVariable];
  if (!selector) return true;
  return selector === testInfo.title || selector === flowId(testInfo);
}

async function createFixture(page, testInfo, use) {
  testInfo.skip(!selected(testInfo), `Skipped by ${selectorVariable}`);
  const outputRoot = process.env.PRWITNESS_CAPTURE_DIR;
  const side = process.env.PRWITNESS_SIDE === "base" ? "base" : "head";
  const id = flowId(testInfo);
  const directory = outputRoot
    ? join(outputRoot, id)
    : testInfo.outputPath("prwitness");
  const screenshotDirectory = join(directory, "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });

  const captures = [];
  const requirements = [];
  const issues = [];
  const notes = [];
  const proof = {
    async capture(name) {
      const safeName = safeSegment(name);
      const path = join(screenshotDirectory, `${safeName}.png`);
      await page.screenshot({ path });
      captures.push({
        name: safeName,
        path: relative(directory, path).replaceAll("\\", "/"),
      });
    },
    async note(value) { notes.push(String(value)); },
    async requirements(values) { requirements.push(...values.map(String)); },
    async highlight() {},
    async mask() {},
    async redact() {},
  };

  let fixtureError;
  const onConsole = (message) => {
    if (message.type() === "error") issues.push({ type: "console", message: message.text() });
  };
  const onPageError = (error) => issues.push({ type: "page", message: error.message });
  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  try {
    await use(proof);
  } catch (error) {
    fixtureError = error;
  } finally {
    const status = fixtureError || testInfo.status !== testInfo.expectedStatus ? "failed" : "passed";
    await writeFile(join(directory, "logs.json"), `${JSON.stringify({ issues }, null, 2)}\n`);
    await writeFile(
      join(directory, "flow.json"),
      `${JSON.stringify({
        id,
        name: testInfo.title,
        side,
        status,
        durationMs: 1,
        viewport: { name: testInfo.project.name || "default", width: 1280, height: 720 },
        requirements: requirements.map((text) => ({ text, result: status === "passed" ? "pass" : "fail", evidence: captures.map((capture) => capture.path) })),
        captures,
        notes,
        issues,
        logs: "logs.json",
      }, null, 2)}\n`,
    );
  }
  if (fixtureError) throw fixtureError;
}

const proofTest = base.extend({
  proof: async ({ page }, use, testInfo) => createFixture(page, testInfo, use),
});

export { expect, flowId, proofTest, selectorVariable };
