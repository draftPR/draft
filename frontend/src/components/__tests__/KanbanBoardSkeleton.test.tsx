import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { KanbanBoardSkeleton } from "../skeletons/KanbanBoardSkeleton";

describe("KanbanBoardSkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<KanbanBoardSkeleton />);

    expect(container.firstChild).toBeInTheDocument();
  });

  it("renders column headers with state display names", () => {
    render(<KanbanBoardSkeleton />);

    // The skeleton renders STATE_DISPLAY_NAMES for each column
    expect(screen.getByText("Proposed")).toBeInTheDocument();
    expect(screen.getByText("Planned")).toBeInTheDocument();
    expect(screen.getByText("Executing")).toBeInTheDocument();
    expect(screen.getByText("Verifying")).toBeInTheDocument();
    expect(screen.getByText("Needs Review")).toBeInTheDocument();
  });

  it("renders skeleton cards in each column", () => {
    const { container } = render(<KanbanBoardSkeleton />);

    // Skeleton cards have a specific CSS class structure
    const skeletonCards = container.querySelectorAll(".bg-card");
    expect(skeletonCards.length).toBeGreaterThan(0);
  });
});
