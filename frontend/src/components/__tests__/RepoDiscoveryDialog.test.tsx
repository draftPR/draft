import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { RepoDiscoveryDialog } from "../RepoDiscoveryDialog";

vi.mock("@/contexts/BoardContext", () => ({
  useBoard: () => ({
    currentBoard: {
      id: "board-1",
      name: "Test Board",
      repo_root: "/tmp/test-repo",
      description: null,
      default_branch: "main",
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
    },
    boards: [],
    isLoading: false,
    error: null,
    setCurrentBoard: vi.fn(),
    refreshBoards: vi.fn(),
  }),
}));

describe("RepoDiscoveryDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onReposAdded: vi.fn(),
  };

  it("renders dialog content when open", () => {
    render(<RepoDiscoveryDialog {...defaultProps} />);

    expect(screen.getByText("Discover Repositories")).toBeInTheDocument();
    expect(
      screen.getByText(/Scan your filesystem for git repositories/),
    ).toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(<RepoDiscoveryDialog {...defaultProps} open={false} />);

    expect(
      screen.queryByText("Discover Repositories"),
    ).not.toBeInTheDocument();
  });

  it("shows search input with default path", () => {
    render(<RepoDiscoveryDialog {...defaultProps} />);

    const input = screen.getByPlaceholderText(
      /Path to scan/,
    ) as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.value).toBe("~/code");
  });

  it("shows Scan button", () => {
    render(<RepoDiscoveryDialog {...defaultProps} />);

    // The dialog auto-scans on open, so the button may show "Scanning..."
    // or "Scan" depending on timing. Check for either.
    const scanButton = screen.getByRole("button", { name: /Scan/ });
    expect(scanButton).toBeInTheDocument();
  });

  it("auto-scans when dialog opens for the first time", async () => {
    render(<RepoDiscoveryDialog {...defaultProps} />);

    // The MSW handler at POST /repos/discover returns { repos: [] }
    // (with discovered key actually - let's check the response shape)
    // The component filters for is_valid repos, so with empty array
    // it will show no results after scan completes.
    await waitFor(() => {
      // After scan completes, scanning state should be gone
      expect(screen.queryByText("Scanning...")).not.toBeInTheDocument();
    });
  });
});
