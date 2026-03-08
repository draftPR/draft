import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { TicketCard } from "@/components/TicketCard";
import { TicketState } from "@/types/api";
import type { Ticket } from "@/types/api";

vi.mock("@hello-pangea/dnd", () => ({
  DragDropContext: ({ children }: { children: React.ReactNode }) => children,
  Droppable: ({ children }: { children: (...args: unknown[]) => React.ReactNode }) =>
    children(
      { innerRef: vi.fn(), droppableProps: {}, placeholder: null },
      {}
    ),
  Draggable: ({ children }: { children: (...args: unknown[]) => React.ReactNode }) =>
    children(
      { innerRef: vi.fn(), draggableProps: {}, dragHandleProps: {} },
      { isDragging: false }
    ),
}));

const baseTicket: Ticket = {
  id: "ticket-1",
  goal_id: "goal-1",
  title: "Fix login button",
  description: "The login button does not respond on mobile",
  state: TicketState.PLANNED,
  priority: 75,
  blocked_by_ticket_id: null,
  blocked_by_ticket_title: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

describe("TicketCard", () => {
  it("renders the ticket title", () => {
    render(
      <TicketCard ticket={baseTicket} index={0} onClick={vi.fn()} />
    );
    expect(screen.getByText("Fix login button")).toBeInTheDocument();
  });

  it("renders the ticket description", () => {
    render(
      <TicketCard ticket={baseTicket} index={0} onClick={vi.fn()} />
    );
    expect(
      screen.getByText("The login button does not respond on mobile")
    ).toBeInTheDocument();
  });

  it("does not render description when absent", () => {
    const ticket = { ...baseTicket, description: null };
    render(
      <TicketCard ticket={ticket} index={0} onClick={vi.fn()} />
    );
    expect(
      screen.queryByText("The login button does not respond on mobile")
    ).not.toBeInTheDocument();
  });

  it("calls onClick when card is clicked", async () => {
    const onClick = vi.fn();
    render(
      <TicketCard ticket={baseTicket} index={0} onClick={onClick} />,
    );

    const card = screen.getByText("Fix login button").closest("div[class*='cursor-pointer']") as HTMLElement | null;
    if (card) {
      await card.click();
    }
    expect(onClick).toHaveBeenCalledWith(baseTicket);
  });

  it("shows execute button for PLANNED tickets when onExecute is provided", () => {
    render(
      <TicketCard
        ticket={baseTicket}
        index={0}
        onClick={vi.fn()}
        onExecute={vi.fn()}
      />
    );
    expect(
      screen.getByTitle("Execute this ticket")
    ).toBeInTheDocument();
  });

  it("does not show execute button for non-PLANNED tickets", () => {
    const ticket = { ...baseTicket, state: TicketState.EXECUTING };
    render(
      <TicketCard
        ticket={ticket}
        index={0}
        onClick={vi.fn()}
        onExecute={vi.fn()}
      />
    );
    expect(
      screen.queryByTitle("Execute this ticket")
    ).not.toBeInTheDocument();
  });

  it("shows delete button", () => {
    render(
      <TicketCard ticket={baseTicket} index={0} onClick={vi.fn()} />
    );
    expect(
      screen.getByTitle("Delete this ticket")
    ).toBeInTheDocument();
  });

  it("shows lock icon and disables execute when ticket is blocked", () => {
    const blockedTicket: Ticket = {
      ...baseTicket,
      blocked_by_ticket_id: "ticket-0",
      blocked_by_ticket_title: "Setup database",
    };
    render(
      <TicketCard
        ticket={blockedTicket}
        index={0}
        onClick={vi.fn()}
        onExecute={vi.fn()}
      />
    );
    expect(
      screen.getByTitle("Cannot execute: blocked by dependency")
    ).toBeInTheDocument();
  });
});
