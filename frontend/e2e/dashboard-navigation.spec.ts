import { expect, test, type Page } from "@playwright/test";

const email = "dash-867367761dacb@local.test";
const password = "StrongPass1";

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "sql-copilot-ui",
      JSON.stringify({
        state: { sidebarCollapsed: false, theme: "light", history: [] },
        version: 0
      })
    );
  });
});

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 5_000 }).catch(() => null);
  if (!/\/dashboard/.test(page.url())) {
    await page.goto("/signup");
    await page.getByLabel("Name").fill("Dashboard Nav Test");
    await page.getByLabel("Email").fill(`dash-nav-${Date.now()}@local.test`);
    await page.getByLabel("Password", { exact: true }).fill("BrowserPass1!");
    await page.getByLabel("Confirm password").fill("BrowserPass1!");
    await page.getByRole("button", { name: "Create account" }).click();
  }
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test("dashboard navigation stays visible and interactive in light mode", async ({ page }) => {
  await signIn(page);

  const sidebarCopilotLink = page.locator("aside").getByRole("link", { name: "SQL Copilot" });
  await expect(sidebarCopilotLink).toBeVisible();
  await sidebarCopilotLink.hover();
  const sidebarHoverColor = await sidebarCopilotLink.evaluate((element) => getComputedStyle(element).color);
  expect(sidebarHoverColor).not.toBe("rgb(255, 255, 255)");

  const sidebarIconCount = await page.locator("aside nav a > span[aria-hidden='true']").count();
  expect(sidebarIconCount).toBeGreaterThanOrEqual(9);

  await page.getByRole("button", { name: "Jump to workspace page" }).click();
  await page.getByRole("menuitem", { name: "Schema Graph" }).click();
  await expect(page).toHaveURL(/\/schema-graph$/);
  await expect(page.getByRole("heading", { name: "Schema Graph" })).toBeVisible();

  await page.getByRole("button", { name: "Jump to workspace page" }).click();
  await page.getByRole("menuitem", { name: "Dashboard" }).click();
  await expect(page).toHaveURL(/\/dashboard(?:\?range=\w+)?$/);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  const firstMetricBox = await page.getByRole("button", { name: "Open Planner Accuracy details" }).boundingBox();
  const monthButton = page.getByRole("button", { name: "Month", exact: true });
  const monthBox = await monthButton.boundingBox();
  const chartBox = await page.getByText("Query Analytics").boundingBox();
  expect(firstMetricBox).not.toBeNull();
  expect(monthBox).not.toBeNull();
  expect(chartBox).not.toBeNull();
  expect(monthBox!.y).toBeGreaterThan(firstMetricBox!.y);
  expect(monthBox!.y).toBeLessThan(chartBox!.y);

  await monthButton.click();
  await expect(page).toHaveURL(/range=month/);
  await page.reload();
  await expect(page.getByRole("button", { name: "Month", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "Relationships" }).first().click();
  await expect(page.getByRole("heading", { name: "Relationship Graph" })).toBeVisible();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
});
