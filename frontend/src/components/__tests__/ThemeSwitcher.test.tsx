import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeSwitcher } from "../ThemeSwitcher";

// Mock the theme functions so we don't modify the real DOM/localStorage
vi.mock("../../styles/themes", async () => {
  const actual = await vi.importActual<typeof import("../../styles/themes")>(
    "../../styles/themes",
  );
  return {
    ...actual,
    applyTheme: vi.fn(),
    getCurrentTheme: vi.fn(() => "dark"),
    saveThemePreference: vi.fn(),
  };
});

import { applyTheme, saveThemePreference } from "../../styles/themes";

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("buttons variant", () => {
    it("renders three theme buttons", () => {
      render(<ThemeSwitcher variant="buttons" />);

      expect(screen.getByTitle("Light theme")).toBeInTheDocument();
      expect(screen.getByTitle("Dark theme")).toBeInTheDocument();
      expect(screen.getByTitle("HUD mode (monitoring)")).toBeInTheDocument();
    });

    it("switches to light theme on click", async () => {
      const user = userEvent.setup();
      render(<ThemeSwitcher variant="buttons" />);

      await user.click(screen.getByTitle("Light theme"));

      expect(saveThemePreference).toHaveBeenCalledWith("light");
      expect(applyTheme).toHaveBeenCalledWith("light");
    });

    it("switches to dark theme on click", async () => {
      const user = userEvent.setup();
      render(<ThemeSwitcher variant="buttons" />);

      await user.click(screen.getByTitle("Dark theme"));

      expect(saveThemePreference).toHaveBeenCalledWith("dark");
      expect(applyTheme).toHaveBeenCalledWith("dark");
    });

    it("switches to HUD theme on click", async () => {
      const user = userEvent.setup();
      render(<ThemeSwitcher variant="buttons" />);

      await user.click(screen.getByTitle("HUD mode (monitoring)"));

      expect(saveThemePreference).toHaveBeenCalledWith("hud");
      expect(applyTheme).toHaveBeenCalledWith("hud");
    });
  });

  describe("dropdown variant (default)", () => {
    it("renders a dropdown trigger", () => {
      render(<ThemeSwitcher />);

      // The SelectTrigger should be present as a button-like element
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });
  });
});
