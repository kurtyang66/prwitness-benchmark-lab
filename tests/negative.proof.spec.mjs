import { proofTest as test, expect } from "@prwitness/playwright";

for (let number = 1; number <= 10; number += 1) {
  const flow = String(number).padStart(2, "0");
  test(`Hold Flow ${flow}`, { tag: "@proof" }, async ({ page, proof }) => {
    await proof.requirements([`Synthetic HOLD flow ${flow} renders in the browser`]);
    await page.goto(`/?flow=hold-${flow}`);
    await expect(page.getByRole("heading", { name: "PRWitness benchmark fixture" })).toBeVisible();
    await proof.capture(`hold-flow-${flow}`);
    if (flow === "02") {
      await expect(page.getByRole("heading", { name: "intentionally missing state" })).toBeVisible();
    }
  });
}
