import { test, expect } from "@playwright/test";
import { mockAllApiRoutes } from "./fixtures";

test.describe("Goal Management", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiRoutes(page);
  });

  test("create goal via dialog", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
    await page.getByRole("button", { name: /New Goal/i }).click();
    await expect(
      page.getByRole("heading", { name: /Create New Goal/i }),
    ).toBeVisible();
  });

  test("goals list shows goals from API", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
    // Click the Goals button in the header (exact match to avoid "New Goal")
    await page
      .locator("header")
      .getByRole("button", { name: /^Goals$/i })
      .click();
    await expect(page.getByText("Test Goal").first()).toBeVisible();
  });
});
