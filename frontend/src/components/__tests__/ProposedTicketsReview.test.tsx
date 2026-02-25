import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { ProposedTicketsReview } from "@/components/ProposedTicketsReview";
import type { ProposedTicket } from "@/types/api";

vi.mock("@/services/api", () => ({
  bulkAcceptTickets: vi.fn(),
}));

const mockTickets: ProposedTicket[] = [
  {
    id: "pt-1",
    title: "Fix login bug",
    description: "The login button is broken on mobile devices",
    verification: ["npm test", "npm run lint"],
    notes: "Affects iOS Safari",
  },
  {
    id: "pt-2",
    title: "Add unit tests",
    description: "Add test coverage for auth module",
    verification: ["pytest -q"],
    notes: null,
  },
];

describe("ProposedTicketsReview", () => {
  it("renders the header with ticket count", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    expect(
      screen.getByText("AI-Suggested Tickets (2)"),
    ).toBeInTheDocument();
  });

  it("renders all ticket titles", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    expect(screen.getByText("Fix login bug")).toBeInTheDocument();
    expect(screen.getByText("Add unit tests")).toBeInTheDocument();
  });

  it("renders ticket descriptions", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    // Descriptions appear in the header (line-clamp-2)
    expect(
      screen.getAllByText(
        "The login button is broken on mobile devices",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("renders Select All and Deselect All buttons", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    expect(screen.getByText("Select All")).toBeInTheDocument();
    expect(screen.getByText("Deselect All")).toBeInTheDocument();
  });

  it("renders Cancel button", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("renders Accept button with count (all selected by default)", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    expect(screen.getByText("Accept (2)")).toBeInTheDocument();
  });

  it("renders Accept & Queue button", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    expect(screen.getByText("Accept & Queue")).toBeInTheDocument();
  });

  it("renders selection count in footer", () => {
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={vi.fn()}
        onAccepted={vi.fn()}
      />,
    );
    expect(screen.getByText("2 of 2 selected")).toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    render(
      <ProposedTicketsReview
        tickets={mockTickets}
        goalId="goal-1"
        onClose={onClose}
        onAccepted={vi.fn()}
      />,
    );
    screen.getByText("Cancel").click();
    expect(onClose).toHaveBeenCalled();
  });
});
