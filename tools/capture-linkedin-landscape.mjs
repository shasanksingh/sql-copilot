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

async function prepareLightTheme(page) {
  await page.addInitScript(() => {
    localStorage.setItem("sql-copilot-ui", JSON.stringify({
      state: {
        sidebarCollapsed: false,
        theme: "light",
        history: []
      },
      version: 0
    }));
  });
}

async function ensureLightAuthSurface(page) {
  await page.addStyleTag({
    content: `
      html.light .auth-shell { background: #f8fafc !important; }
      html.light .auth-shell > .pointer-events-none {
        background:
          radial-gradient(circle at 15% 20%, rgba(14, 116, 144, 0.11), transparent 27%),
          radial-gradient(circle at 72% 0%, rgba(67, 56, 202, 0.11), transparent 28%),
          linear-gradient(rgba(100, 116, 139, 0.09) 1px, transparent 1px),
          linear-gradient(90deg, rgba(100, 116, 139, 0.09) 1px, transparent 1px) !important;
        background-size: auto, auto, 44px 44px, 44px 44px !important;
      }
      html.light .auth-shell .auth-form-surface {
        background: rgba(255, 255, 255, 0.96) !important;
        border-color: rgba(14, 116, 144, 0.20) !important;
        box-shadow: 0 24px 64px rgba(15, 23, 42, 0.12) !important;
      }
      html.light .auth-shell .auth-form-surface h2,
      html.light .auth-shell .auth-form-surface .text-white { color: #0f172a !important; }
      html.light .auth-shell .auth-form-surface .text-slate-300,
      html.light .auth-shell .auth-form-surface .text-slate-400,
      html.light .auth-shell .auth-form-surface .text-cyan-100 { color: #475569 !important; }
      html.light .auth-shell .auth-form-surface input,
      html.light .auth-shell .auth-form-surface select {
        background: #ffffff !important;
        color: #0f172a !important;
        border-color: rgba(15, 23, 42, 0.14) !important;
      }
    `
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.setDefaultTimeout(30_000);
    page.setDefaultNavigationTimeout(30_000);

    await prepareLightTheme(page);
    await page.goto(`${baseUrl}/signup`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Create your account" }).waitFor({ state: "visible" });
    await page.locator("html.light").waitFor({ state: "attached" });
    await ensureLightAuthSurface(page);
    await capture(page, "00-signup-light-landscape.png");

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

    await page.getByRole("link", { name: "Schema Explorer" }).click();
    await page.waitForURL(/\/schema-explorer$/, { timeout: 15_000 });
    await page.getByRole("heading", { name: "Schema Explorer" }).waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForTimeout(1_500);
    await capture(page, "03-schema-explorer-light-landscape.png");

    await page.getByRole("link", { name: "Schema Graph" }).click();
    await page.waitForURL(/\/schema-graph$/, { timeout: 15_000 });
    await page.getByRole("heading", { name: "Schema Graph" }).waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForTimeout(1_500);
    await capture(page, "04-schema-graph-light-landscape.png");

    await page.getByRole("link", { name: "SQL Repair" }).click();
    await page.waitForURL(/\/sql-repair$/, { timeout: 15_000 });
    await page.locator("textarea").first().fill("SELEC employee_id FROM employees");
    await page.getByRole("button", { name: "Check and correct" }).click();
    await page.getByRole("heading", { name: "Corrected statement" }).waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForTimeout(5_200);
    await capture(page, "05-sql-repair-light-landscape.png");

    console.log(JSON.stringify({ email, outputDirectory }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
