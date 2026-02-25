import { test, expect } from "@playwright/test";
import { mockAllApiRoutes } from "./fixtures";

test.describe("Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiRoutes(page);
  });

  test("root route shows kanban board", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Planned").first()).toBeVisible();
  });

  test("settings route shows settings page", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /Settings/i, level: 1 }),
    ).toBeVisible();
  });

  test("navigating to unknown route redirects to root", async ({ page }) => {
    await page.goto("/nonexistent");
    await expect(
      page.locator("header").getByText("Alma Kanban"),
    ).toBeVisible();
  });

  test("keyboard shortcut ? opens help", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
    await page.keyboard.press("?");
    await expect(
      page.getByRole("heading", { name: /Keyboard Shortcuts/i }),
    ).toBeVisible();
  });
});
