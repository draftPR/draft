import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import userEvent from "@testing-library/user-event";
import { CreateGoalDialog } from "../CreateGoalDialog";

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

describe("CreateGoalDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onSuccess: vi.fn(),
  };

  it("renders dialog content when open", () => {
    render(<CreateGoalDialog {...defaultProps} />);

    expect(screen.getByText("Create New Goal")).toBeInTheDocument();
    expect(
      screen.getByText(/Goals help organize related tickets/),
    ).toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(<CreateGoalDialog {...defaultProps} open={false} />);

    expect(screen.queryByText("Create New Goal")).not.toBeInTheDocument();
  });

  it("shows title and description form fields", () => {
    render(<CreateGoalDialog {...defaultProps} />);

    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Enter goal title..."),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Describe the goal... (optional)"),
    ).toBeInTheDocument();
  });

  it("shows Create Goal and Cancel buttons", () => {
    render(<CreateGoalDialog {...defaultProps} />);

    expect(
      screen.getByRole("button", { name: "Create Goal" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancel" }),
    ).toBeInTheDocument();
  });

  it("calls onOpenChange(false) when Cancel is clicked", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();

    render(
      <CreateGoalDialog
        {...defaultProps}
        onOpenChange={onOpenChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows validation error when submitting empty title", async () => {
    const user = userEvent.setup();

    render(<CreateGoalDialog {...defaultProps} />);

    await user.click(screen.getByRole("button", { name: "Create Goal" }));

    expect(screen.getByText("Title is required")).toBeInTheDocument();
  });

  it("submits the form with a valid title", async () => {
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <CreateGoalDialog
        open={true}
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );

    await user.type(screen.getByLabelText("Title"), "My new goal");
    await user.click(screen.getByRole("button", { name: "Create Goal" }));

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
    });
  });

  it("shows Full Autonomy Mode section that expands on click", async () => {
    const user = userEvent.setup();

    render(<CreateGoalDialog {...defaultProps} />);

    expect(screen.getByText("Full Autonomy Mode")).toBeInTheDocument();

    // Click to expand the autonomy section
    await user.click(screen.getByText("Full Autonomy Mode"));

    expect(screen.getByText("Enable Autonomy")).toBeInTheDocument();
    expect(
      screen.getByText(/Enable autonomous execution/),
    ).toBeInTheDocument();
  });

  it("clears title error when user starts typing", async () => {
    const user = userEvent.setup();

    render(<CreateGoalDialog {...defaultProps} />);

    // Submit empty to trigger error
    await user.click(screen.getByRole("button", { name: "Create Goal" }));
    expect(screen.getByText("Title is required")).toBeInTheDocument();

    // Start typing to clear the error
    await user.type(screen.getByLabelText("Title"), "a");

    expect(screen.queryByText("Title is required")).not.toBeInTheDocument();
  });
});
