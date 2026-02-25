import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { ExecutorSelector } from "@/components/ExecutorSelector";

vi.mock("@/hooks/useAvailableExecutors", () => ({
  useAvailableExecutors: vi.fn(),
}));

import { useAvailableExecutors } from "@/hooks/useAvailableExecutors";

describe("ExecutorSelector", () => {
  it("renders loading state", () => {
    vi.mocked(useAvailableExecutors).mockReturnValue({
      executors: [],
      loading: true,
      error: null,
    });

    render(
      <ExecutorSelector value="claude" onValueChange={vi.fn()} />,
    );
    expect(screen.getByText("Loading executors...")).toBeInTheDocument();
  });

  it("renders error state", () => {
    vi.mocked(useAvailableExecutors).mockReturnValue({
      executors: [],
      loading: false,
      error: "Network error",
    });

    render(
      <ExecutorSelector value="claude" onValueChange={vi.fn()} />,
    );
    expect(
      screen.getByText(/Failed to load executors: Network error/),
    ).toBeInTheDocument();
  });

  it("renders the select trigger with loaded executors", () => {
    vi.mocked(useAvailableExecutors).mockReturnValue({
      executors: [
        {
          name: "claude",
          display_name: "Claude Code",
          version: "1.0.0",
          capabilities: ["streaming_output", "yolo_mode"],
          config_schema: {},
          available: true,
        },
      ],
      loading: false,
      error: null,
    });

    render(
      <ExecutorSelector value="claude" onValueChange={vi.fn()} />,
    );
    // Help text should be visible
    expect(
      screen.getByText(/Select which AI coding agent/),
    ).toBeInTheDocument();
  });
});
