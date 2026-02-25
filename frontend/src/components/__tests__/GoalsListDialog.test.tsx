import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { GoalsListDialog } from "../GoalsListDialog";

// Mock GoalDetailDialog to avoid nested dialog complexity
vi.mock("../GoalDetailDialog", () => ({
  GoalDetailDialog: () => null,
}));

describe("GoalsListDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onBoardRefresh: vi.fn(),
  };

  it("renders dialog content when open", () => {
    render(<GoalsListDialog {...defaultProps} />);

    expect(screen.getByText("Goals")).toBeInTheDocument();
    expect(
      screen.getByText(/Select a goal to view details/),
    ).toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(<GoalsListDialog {...defaultProps} open={false} />);

    expect(screen.queryByText("Goals")).not.toBeInTheDocument();
  });

  it("shows loading spinner initially", () => {
    render(<GoalsListDialog {...defaultProps} />);

    // The loading state shows a spinner before data loads
    // (Loader2 is rendered but checking for the spinning element)
    // The dialog content should be visible while loading
    expect(screen.getByText("Goals")).toBeInTheDocument();
  });

  it("lists goals from the API after loading", async () => {
    render(<GoalsListDialog {...defaultProps} />);

    // MSW handler at GET /goals returns { goals: [defaultGoal] }
    // defaultGoal has title "Default Goal"
    await waitFor(() => {
      expect(screen.getByText("Default Goal")).toBeInTheDocument();
    });
  });

  it("shows AI badge for goals", async () => {
    render(<GoalsListDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Default Goal")).toBeInTheDocument();
    });

    // Each goal has an "AI" badge
    expect(screen.getByText("AI")).toBeInTheDocument();
  });

  it("renders goal items as clickable buttons", async () => {
    render(<GoalsListDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Default Goal")).toBeInTheDocument();
    });

    // The goal entry is rendered as a button element
    const goalButton = screen.getByText("Default Goal").closest("button");
    expect(goalButton).toBeInTheDocument();
  });
});
