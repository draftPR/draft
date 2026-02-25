import { test, expect } from "@playwright/test";
import { mockAllApiRoutes } from "./fixtures";

test.describe("Ticket Lifecycle", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiRoutes(page);
  });

  test("create ticket via dialog", async ({ page }) => {
    await page.goto("/");
    // Wait for board to load first
    await expect(page.getByText("Setup database schema")).toBeVisible();
    await page.getByRole("button", { name: /New Ticket/i }).click();
    // Dialog should show the title
    await expect(
      page.getByRole("heading", { name: /Create New Ticket/i }),
    ).toBeVisible();
  });

  test("ticket card shows title", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
  });

  test("clicking a ticket opens detail panel", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema").first()).toBeVisible();
    // Click the ticket card
    await page.getByText("Setup database schema").first().click();
    // Detail panel should open showing the ticket title in an h2 heading
    await expect(
      page.locator("h2", { hasText: "Setup database schema" }),
    ).toBeVisible({ timeout: 10000 });
  });
});
