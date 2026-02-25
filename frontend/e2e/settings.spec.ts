import { test, expect } from "@playwright/test";
import { mockAllApiRoutes } from "./fixtures";

test.describe("Settings Page", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiRoutes(page);
  });

  test("renders settings heading", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /Settings/i, level: 1 }),
    ).toBeVisible();
  });

  test("shows tab navigation", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("tab", { name: /General/i })).toBeVisible();
  });
});
