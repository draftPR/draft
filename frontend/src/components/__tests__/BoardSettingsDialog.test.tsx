import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { BoardSettingsDialog } from "../BoardSettingsDialog";

const BASE = "http://localhost:8000";

// Override the board config handler to return a full config response
beforeEach(() => {
  server.use(
    http.get(`${BASE}/boards/:boardId/config`, () =>
      HttpResponse.json({
        has_overrides: false,
        config: {
          execute_config: {
            executor_model: "auto",
            timeout: 300,
            preferred_executor: "cursor-agent",
          },
        },
      }),
    ),
    http.get(`${BASE}/executors/:executor/models`, () =>
      HttpResponse.json([
        { id: "auto", name: "Auto", description: "Intelligent model selection" },
        { id: "claude-sonnet", name: "Claude Sonnet", description: "Fast and capable" },
      ]),
    ),
  );
});

describe("BoardSettingsDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    boardId: "board-1",
    onTicketsDeleted: vi.fn(),
  };

  it("renders dialog content when open", async () => {
    render(<BoardSettingsDialog {...defaultProps} />);

    // Initially shows loading, then the form loads
    await waitFor(() => {
      expect(screen.getByText("Board Settings")).toBeInTheDocument();
    });
  });

  it("does not render dialog content when closed", () => {
    render(<BoardSettingsDialog {...defaultProps} open={false} />);

    expect(screen.queryByText("Board Settings")).not.toBeInTheDocument();
  });

  it("shows executor and timeout settings after loading", async () => {
    render(<BoardSettingsDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Board Settings")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Execution Model")).toBeInTheDocument();
    });

    expect(screen.getByText("Execution Timeout")).toBeInTheDocument();
    expect(screen.getByText("Preferred Executor")).toBeInTheDocument();
  });

  it("shows Save and Cancel buttons", async () => {
    render(<BoardSettingsDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Board Settings")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Save" }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByRole("button", { name: "Cancel" }),
    ).toBeInTheDocument();
  });

  it("shows Danger Zone section with delete button", async () => {
    render(<BoardSettingsDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Danger Zone")).toBeInTheDocument();
    });

    expect(
      screen.getByRole("button", { name: /Delete All Tickets/ }),
    ).toBeInTheDocument();
  });

  it("shows Reset to YAML button (disabled when no overrides)", async () => {
    render(<BoardSettingsDialog {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Reset to YAML/ }),
      ).toBeInTheDocument();
    });

    // has_overrides is false, so the reset button should be disabled
    expect(
      screen.getByRole("button", { name: /Reset to YAML/ }),
    ).toBeDisabled();
  });

  it("shows override alert when board has custom settings", async () => {
    server.use(
      http.get(`${BASE}/boards/:boardId/config`, () =>
        HttpResponse.json({
          has_overrides: true,
          config: {
            execute_config: {
              executor_model: "claude-sonnet",
              timeout: 600,
              preferred_executor: "claude",
            },
          },
        }),
      ),
    );

    render(<BoardSettingsDialog {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText(/This board has custom settings/),
      ).toBeInTheDocument();
    });
  });
});
