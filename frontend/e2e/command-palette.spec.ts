import { test, expect } from "@playwright/test";
import { mockAllApiRoutes } from "./fixtures";

test.describe("Command Palette", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiRoutes(page);
  });

  test("opens with Ctrl+K", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
    // CommandPalette listens for both metaKey and ctrlKey
    await page.keyboard.press("Control+k");
    await expect(page.getByText("Create New Ticket")).toBeVisible();
  });

  test("shows commands in palette", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
    await page.keyboard.press("Control+k");
    await expect(page.getByText("Create New Ticket")).toBeVisible();
    await expect(page.getByText("Create New Goal")).toBeVisible();
  });

  test("closes with Escape", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();
    await page.keyboard.press("Control+k");
    await expect(page.getByText("Create New Ticket")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByText("Create New Ticket")).toBeHidden();
  });
});
