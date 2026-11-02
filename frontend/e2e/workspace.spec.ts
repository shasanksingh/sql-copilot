import { expect, test, type Page } from "@playwright/test";

let browserErrors: string[] = [];
const frontendPort = process.env.E2E_FRONTEND_PORT ?? "3100";
const localhostBaseURL = `http://localhost:${frontendPort}`;

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
  await page.getByLabel("Your answer").fill("Pune");
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

  await page.goto(`${localhostBaseURL}/signup`);
  await page.getByLabel("Name").fill("E2E Login User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByLabel("Your answer").fill("Pune");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(`${localhostBaseURL}/dashboard`);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.context().clearCookies();
  await page.goto(`${localhostBaseURL}/login`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(`${localhostBaseURL}/dashboard`);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});

test("desktop chat keeps suggestions above the stable composer", async ({ page }) => {
  await createAccount(page, "desktop");
  await page.goto("/copilot");

  const textarea = page.getByPlaceholder("Ask for SQL in natural language");
  await expect(page.getByText(/live tables, relationship map/i)).toBeVisible({ timeout: 30_000 });
  const suggestion = page.getByRole("button", { name: /^(List|Show|Count|Total|Trend)\s/i }).first();
  await expect(textarea).toBeVisible();
  await expect(suggestion).toBeVisible();
  await suggestion.scrollIntoViewIfNeeded();

  const suggestionBox = await suggestion.boundingBox();
  const textareaBox = await textarea.boundingBox();
  expect(suggestionBox).not.toBeNull();
  expect(textareaBox).not.toBeNull();
  expect(suggestionBox!.y + suggestionBox!.height).toBeLessThanOrEqual(textareaBox!.y);

  await textarea.fill("Show all active projects");
  await page.getByRole("button", { name: "Generate SQL" }).click();
  await expect(page.getByText("Reviewed SQL").last()).toBeVisible({ timeout: 30_000 });
  await expect(textarea).toBeVisible();
  await expect(page.getByRole("button", { name: /^(List|Show|Count|Total|Trend)\sProjects/i }).first()).toBeVisible();
  await expect(page.getByText(/live tables, relationship map/i)).toBeVisible();

  const viewport = page.viewportSize();
  const settledBox = await textarea.boundingBox();
  expect(settledBox).not.toBeNull();
  expect(settledBox!.y + settledBox!.height).toBeLessThanOrEqual(viewport!.height);

  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.getByTitle("Dashboard")).toBeVisible();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  await expect(page.getByText("Enterprise analytics workspace")).toBeHidden();
});

test("chat downloads only reviewed SQL as a .sql file", async ({ page }) => {
  await createAccount(page, "sql-export");
  await page.goto("/copilot");

  const textarea = page.getByPlaceholder("Ask for SQL in natural language");
  await textarea.fill("Show all customer details");
  await page.getByRole("button", { name: "Generate SQL" }).click();
  await expect(page.getByText("Reviewed SQL").last()).toBeVisible({ timeout: 30_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download reviewed SQL" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^sql-copilot-queries-\d{4}-\d{2}-\d{2}\.sql$/);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const contents = Buffer.concat(chunks).toString("utf8");
  expect(contents).toContain("SELECT *\nFROM clients;");
  expect(contents).not.toContain('"insights"');
  expect(contents).not.toContain("nvidia/");
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
