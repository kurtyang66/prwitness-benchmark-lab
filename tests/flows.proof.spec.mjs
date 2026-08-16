import { proofTest as test, expect } from "@prwitness/playwright";

for (let number = 1; number <= 25; number += 1) {
  const flow = String(number).padStart(2, "0");
  test(`Flow ${flow}`, { tag: "@proof" }, async ({ page, proof }) => {
    await proof.requirements([`Synthetic benchmark flow ${flow} renders in the browser`]);
    await page.goto(`/?flow=${flow}`);
    await expect(page.getByRole("heading", { name: "PRWitness benchmark fixture" })).toBeVisible();
    await expect(page.getByTestId("flow-id")).toHaveText(`flow-${flow}`);
    await proof.capture(`flow-${flow}`);
  });
}
