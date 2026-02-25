import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { TicketDetailDrawer } from "@/components/TicketDetailDrawer";
import { TicketState, STATE_DISPLAY_NAMES } from "@/types/api";
import type { Ticket } from "@/types/api";

const mockTicket: Ticket = {
  id: "ticket-2",
  goal_id: "goal-1",
  title: "Add dark mode support",
  description: "Implement theme switching with Tailwind dark mode",
  state: TicketState.NEEDS_HUMAN,
  priority: 50,
  blocked_by_ticket_id: null,
  blocked_by_ticket_title: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

// Mock API calls
vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    fetchTicketEvents: vi.fn().mockResolvedValue({ events: [] }),
    fetchTicketEvidence: vi.fn().mockResolvedValue({ evidence: [] }),
    fetchTicketRevisions: vi.fn().mockResolvedValue({ revisions: [] }),
    fetchMergeStatus: vi.fn().mockResolvedValue(null),
    mergeTicket: vi.fn(),
    fetchTicketJobs: vi.fn().mockResolvedValue({ jobs: [] }),
    fetchTicketDependents: vi.fn().mockResolvedValue([]),
    fetchTicketAgentLogs: vi.fn().mockResolvedValue({
      ticket_id: "ticket-2",
      total_jobs: 0,
      total_entries: 0,
      executions: [],
    }),
    streamAgentLogs: vi.fn().mockReturnValue({ close: vi.fn() }),
  };
});

describe("TicketDetailDrawer", () => {
  const mockOnOpenChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when ticket is null", () => {
    const { container } = render(
      <TicketDetailDrawer
        ticket={null}
        open={true}
        onOpenChange={mockOnOpenChange}
      />
    );
    // Should not render any sheet content
    expect(container.innerHTML).toBe("");
  });

  it("renders ticket title when open with a ticket", async () => {
    render(
      <TicketDetailDrawer
        ticket={mockTicket}
        open={true}
        onOpenChange={mockOnOpenChange}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText("Add dark mode support")
      ).toBeInTheDocument();
    });
  });

  it("renders ticket description", async () => {
    render(
      <TicketDetailDrawer
        ticket={mockTicket}
        open={true}
        onOpenChange={mockOnOpenChange}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText("Implement theme switching with Tailwind dark mode")
      ).toBeInTheDocument();
    });
  });

  it("renders state display name", async () => {
    render(
      <TicketDetailDrawer
        ticket={mockTicket}
        open={true}
        onOpenChange={mockOnOpenChange}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText(STATE_DISPLAY_NAMES[TicketState.NEEDS_HUMAN])
      ).toBeInTheDocument();
    });
  });

  it("renders priority display for medium priority ticket", async () => {
    render(
      <TicketDetailDrawer
        ticket={mockTicket}
        open={true}
        onOpenChange={mockOnOpenChange}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("50 (Medium)")).toBeInTheDocument();
    });
  });

  it("shows 'No description provided' when description is empty", async () => {
    const ticketNoDesc = { ...mockTicket, description: null };
    render(
      <TicketDetailDrawer
        ticket={ticketNoDesc}
        open={true}
        onOpenChange={mockOnOpenChange}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText("No description provided")
      ).toBeInTheDocument();
    });
  });

  it("renders section headings", async () => {
    render(
      <TicketDetailDrawer
        ticket={mockTicket}
        open={true}
        onOpenChange={mockOnOpenChange}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Description")).toBeInTheDocument();
      expect(screen.getByText("State")).toBeInTheDocument();
      expect(screen.getByText("Priority")).toBeInTheDocument();
    });
  });
});
