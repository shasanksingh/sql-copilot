import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("../frontend/node_modules/playwright");

const baseUrl = process.env.SQL_COPILOT_LIVE_URL ?? "https://sql-copilot-frontend.singhshasank50.workers.dev";
const outputDirectory = path.resolve(process.env.SQL_COPILOT_CAROUSEL_DIR ?? "artifacts/linkedin-carousel");
const runId = Date.now();
const existingEmail = process.env.SQL_COPILOT_CAPTURE_EMAIL;
const existingPassword = process.env.SQL_COPILOT_CAPTURE_PASSWORD;
const email = existingEmail ?? `linkedin.qa.${runId}@example.com`;
const password = existingPassword ?? "Cobalt!River7Lumen";

fs.mkdirSync(outputDirectory, { recursive: true });
const statusPath = path.join(outputDirectory, "capture-status.txt");

function mark(status) {
  fs.writeFileSync(statusPath, `${new Date().toISOString()} ${status}\n`);
}

async function capture(page, fileName) {
  await page.screenshot({
    path: path.join(outputDirectory, fileName),
    fullPage: false,
  });
}

async function main() {
  mark("launching browser");
  const browser = await chromium.launch({ headless: true });
  try {
  const context = await browser.newContext({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.setDefaultTimeout(25_000);
  page.setDefaultNavigationTimeout(25_000);
  if (existingEmail && existingPassword) {
    mark("loading login");
    await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
    const loginInputs = page.locator("input");
    await loginInputs.nth(0).fill(email);
    await loginInputs.nth(1).fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
    mark("waiting for dashboard after login");
  } else {
    mark("loading signup");
    await page.goto(`${baseUrl}/signup`, { waitUntil: "domcontentloaded" });
    mark("filling signup");
    await capture(page, "00-signup.png");
    const signupInputs = page.locator("input");
    await signupInputs.nth(0).fill("SQL Copilot Demo");
    mark("signup name entered");
    await signupInputs.nth(1).fill(email);
    mark("signup email entered");
    await signupInputs.nth(2).fill(password);
    mark("signup password entered");
    await signupInputs.nth(3).fill(password);
    mark("signup password confirmed");
    await signupInputs.nth(4).fill("Bengaluru");
    mark("signup recovery answer entered");
    await page.getByRole("button", { name: "Create account" }).click();
    mark("waiting for dashboard after signup");
  }
  await page.waitForURL(/\/dashboard$/, { timeout: 30_000 });
  await page.getByRole("heading", { name: "Dashboard" }).waitFor({ state: "visible" });
  mark("capturing dashboard");
  await capture(page, "01-dashboard.png");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await page.waitForTimeout(250);
  await capture(page, "05-light-dashboard.png");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await page.waitForTimeout(250);

  mark("opening copilot");
  await page.getByRole("link", { name: "SQL Copilot" }).click();
  await page.waitForURL(/\/copilot$/, { timeout: 15_000 });
  const textarea = page.getByPlaceholder("Ask for SQL in natural language");
  await textarea.waitFor({ state: "visible", timeout: 30_000 });
  await textarea.fill("Headcount by department");
  await page.getByRole("button", { name: "Generate SQL" }).click();
  mark("waiting for query result");
  await page.getByRole("button", { name: "View review" }).waitFor({ state: "visible", timeout: 45_000 });
  await page.getByRole("button", { name: "View review" }).click();
  await page.getByText("Review scorecard").last().waitFor({ state: "visible", timeout: 15_000 });
  await page.waitForTimeout(3_200);
  await capture(page, "02-query-review.png");
  await page.getByRole("button", { name: "Close review" }).click();
  await page.getByRole("button", { name: "View review" }).waitFor({ state: "visible" });

  mark("opening SQL repair");
  await page.getByRole("link", { name: "SQL Repair" }).click();
  await page.waitForURL(/\/sql-repair$/, { timeout: 15_000 });
  await page.locator("textarea").first().fill("SELEC employee_id FROM employees");
  await page.getByRole("button", { name: "Check and correct" }).click();
  await page.getByRole("heading", { name: "Corrected statement" }).waitFor({ state: "visible", timeout: 30_000 });
  await page.waitForTimeout(5_200);
  await capture(page, "03-sql-repair.png");

  mark("capturing mobile workspace");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/copilot`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("Ask for SQL in natural language").waitFor({ state: "visible", timeout: 30_000 });
  await capture(page, "04-mobile-workspace.png");

  mark("complete");
  console.log(JSON.stringify({ email, outputDirectory }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
