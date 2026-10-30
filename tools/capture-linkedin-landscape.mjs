import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("../frontend/node_modules/playwright");

const baseUrl = process.env.SQL_COPILOT_LIVE_URL ?? "https://sql-copilot.pages.dev";
const outputDirectory = path.resolve(process.env.SQL_COPILOT_LANDSCAPE_DIR ?? "artifacts/linkedin-carousel-landscape");
const runId = Date.now();
const existingEmail = process.env.SQL_COPILOT_CAPTURE_EMAIL;
const existingPassword = process.env.SQL_COPILOT_CAPTURE_PASSWORD;
const email = existingEmail ?? `linkedin.landscape.${runId}@example.com`;
const password = existingPassword ?? "Cobalt!River7Lumen";

fs.mkdirSync(outputDirectory, { recursive: true });

async function capture(page, fileName) {
  await page.screenshot({
    path: path.join(outputDirectory, fileName),
    fullPage: false,
  });
}

async function setLightTheme(page) {
  if (!(await page.locator("html").evaluate((node) => node.classList.contains("light")))) {
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await page.locator("html.light").waitFor({ state: "attached" });
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.setDefaultTimeout(30_000);
    page.setDefaultNavigationTimeout(30_000);

    if (existingEmail && existingPassword) {
      await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
      const loginInputs = page.locator("input");
      await loginInputs.nth(0).fill(email);
      await loginInputs.nth(1).fill(password);
      await page.getByRole("button", { name: "Sign in" }).click();
    } else {
      await page.goto(`${baseUrl}/signup`, { waitUntil: "domcontentloaded" });
      const signupInputs = page.locator("input");
      await signupInputs.nth(0).fill("SQL Copilot Showcase");
      await signupInputs.nth(1).fill(email);
      await signupInputs.nth(2).fill(password);
      await signupInputs.nth(3).fill(password);
      await signupInputs.nth(4).fill("Bengaluru");
      await page.getByRole("button", { name: "Create account" }).click();
    }
    await page.waitForURL(/\/dashboard$/, { timeout: 30_000 });
    await page.getByRole("heading", { name: "Dashboard" }).waitFor({ state: "visible" });

    await setLightTheme(page);
    await capture(page, "01-dashboard-light-landscape.png");

    await page.getByRole("link", { name: "SQL Copilot" }).click();
    await page.waitForURL(/\/copilot$/, { timeout: 15_000 });
    const textarea = page.getByPlaceholder("Ask for SQL in natural language");
    await textarea.waitFor({ state: "visible", timeout: 30_000 });
    await textarea.fill("Headcount by department");
    await page.getByRole("button", { name: "Generate SQL" }).click();
    // At desktop widths the review panel is displayed alongside the SQL result;
    // the "View review" action is intentionally mobile-only.
    await page.getByText("Review scorecard").last().waitFor({ state: "visible", timeout: 100_000 });
    await page.waitForTimeout(3_200);
    await capture(page, "02-query-review-xai-light-landscape.png");

    await page.getByRole("link", { name: "SQL Repair" }).click();
    await page.waitForURL(/\/sql-repair$/, { timeout: 15_000 });
    await page.locator("textarea").first().fill("SELEC employee_id FROM employees");
    await page.getByRole("button", { name: "Check and correct" }).click();
    await page.getByRole("heading", { name: "Corrected statement" }).waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForTimeout(5_200);
    await capture(page, "03-sql-repair-light-landscape.png");

    console.log(JSON.stringify({ email, outputDirectory }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
