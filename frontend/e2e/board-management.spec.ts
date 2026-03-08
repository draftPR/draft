import { test, expect } from "@playwright/test";
import { mockAllApiRoutes } from "./fixtures";

test.describe("Board Management", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiRoutes(page);
  });

  test("loads the app and shows board name", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.locator("header").getByText("Draft"),
    ).toBeVisible();
  });

  test("renders kanban columns", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Planned").first()).toBeVisible();
    await expect(page.getByText("Executing").first()).toBeVisible();
    await expect(page.getByText("Done").first()).toBeVisible();
  });

  test("displays tickets in correct columns", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
    await expect(page.getByText("Implement API endpoints")).toBeVisible();
    await expect(page.getByText("Write tests")).toBeVisible();
  });

  test("board selector shows current board name", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Test Board").first()).toBeVisible();
  });

  test("shows empty state columns for states with no tickets", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText("Proposed").first()).toBeVisible();
  });
});
