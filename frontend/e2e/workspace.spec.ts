import { expect, test, type Page } from "@playwright/test";

let browserErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  browserErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      browserErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
});

test.afterEach(() => {
  expect(browserErrors).toEqual([]);
});

async function createAccount(page: Page, suffix: string) {
  await page.goto("/signup");
  await page.getByLabel("Name").fill(`E2E User ${suffix}`);
  await page.getByLabel("Email").fill(`e2e-${suffix}-${Date.now()}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill("BrowserPass1!");
  await page.getByLabel("Confirm password").fill("BrowserPass1!");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("protected routes redirect to login", async ({ page }) => {
  await page.goto("/copilot");
  await expect(page).toHaveURL(/\/login\?next=%2Fcopilot$/);
});

test("localhost login renders the dashboard after authentication", async ({ page }) => {
  const email = `e2e-login-${Date.now()}@example.com`;
  const password = "BrowserPass1!";

  await page.goto("http://localhost:3000/signup");
  await page.getByLabel("Name").fill("E2E Login User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL("http://localhost:3000/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.context().clearCookies();
  await page.goto("http://localhost:3000/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL("http://localhost:3000/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});

test("desktop chat keeps suggestions above the stable composer", async ({ page }) => {
  await createAccount(page, "desktop");
  await page.goto("/copilot");

  const textarea = page.getByPlaceholder("Ask for SQL in natural language");
  const suggestion = page.getByRole("button", { name: /Top performers by department/ });
  await expect(textarea).toBeVisible();
  await expect(suggestion).toBeVisible();

  const suggestionBox = await suggestion.boundingBox();
  const textareaBox = await textarea.boundingBox();
  expect(suggestionBox).not.toBeNull();
  expect(textareaBox).not.toBeNull();
  expect(suggestionBox!.y + suggestionBox!.height).toBeLessThanOrEqual(textareaBox!.y);

  await textarea.fill("Show all active projects");
  await page.getByRole("button", { name: "Generate SQL" }).click();
  await expect(page.getByText("Valid SQL").last()).toBeVisible({ timeout: 30_000 });
  await expect(textarea).toBeVisible();
  await expect(page.getByRole("button", { name: "Projects ending this month" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Revenue by quarter" })).toBeVisible();

  const viewport = page.viewportSize();
  const settledBox = await textarea.boundingBox();
  expect(settledBox).not.toBeNull();
  expect(settledBox!.y + settledBox!.height).toBeLessThanOrEqual(viewport!.height);

  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.getByTitle("Dashboard")).toBeVisible();
});

test("mobile navigation and composer remain inside the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await createAccount(page, "mobile");
  await page.goto("/copilot");

  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("link", { name: "SQL Copilot" })).toBeVisible();
  await page.getByRole("button", { name: "Close menu" }).click();

  const textarea = page.getByPlaceholder("Ask for SQL in natural language");
  await expect(textarea).toBeVisible();
  const box = await textarea.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
});
