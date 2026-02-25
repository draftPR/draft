import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { AgentActivityLog } from "@/components/AgentActivityLog";

// Mock API
vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    fetchTicketAgentLogs: vi.fn(),
    streamAgentLogs: vi.fn().mockReturnValue({ close: vi.fn() }),
  };
});

const { fetchTicketAgentLogs } = await import("@/services/api");
const mockedFetchLogs = vi.mocked(fetchTicketAgentLogs);

describe("AgentActivityLog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    mockedFetchLogs.mockReturnValue(new Promise(() => {})); // never resolves
    render(<AgentActivityLog ticketId="ticket-1" />);
    expect(
      screen.getByText("Loading agent activity...")
    ).toBeInTheDocument();
  });

  it("shows empty state when no jobs exist", async () => {
    mockedFetchLogs.mockResolvedValue({
      ticket_id: "ticket-1",
      total_jobs: 0,
      total_entries: 0,
      executions: [],
    });

    render(<AgentActivityLog ticketId="ticket-1" />);

    await waitFor(() => {
      expect(
        screen.getByText("No agent activity yet")
      ).toBeInTheDocument();
    });
  });

  it("shows error state with retry button on failure", async () => {
    mockedFetchLogs.mockRejectedValue(new Error("Network error"));

    render(<AgentActivityLog ticketId="ticket-1" />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });

  it("shows execution summary when data is available", async () => {
    mockedFetchLogs.mockResolvedValue({
      ticket_id: "ticket-1",
      total_jobs: 2,
      total_entries: 15,
      executions: [
        {
          job_id: "job-1",
          job_kind: "execute",
          job_status: "succeeded",
          duration_seconds: 120,
          entry_count: 10,
          entries: [],
        },
        {
          job_id: "job-2",
          job_kind: "verify",
          job_status: "succeeded",
          duration_seconds: 30,
          entry_count: 5,
          entries: [],
        },
      ],
    });

    render(<AgentActivityLog ticketId="ticket-1" />);

    await waitFor(() => {
      expect(screen.getByText("2 executions")).toBeInTheDocument();
      expect(screen.getByText("15 entries")).toBeInTheDocument();
    });
  });

  it("renders execution cards for each job", async () => {
    mockedFetchLogs.mockResolvedValue({
      ticket_id: "ticket-1",
      total_jobs: 1,
      total_entries: 3,
      executions: [
        {
          job_id: "job-1",
          job_kind: "execute",
          job_status: "succeeded",
          duration_seconds: 60,
          entry_count: 3,
          entries: [],
        },
      ],
    });

    render(<AgentActivityLog ticketId="ticket-1" />);

    await waitFor(() => {
      expect(screen.getByText("execute")).toBeInTheDocument();
      expect(screen.getByText("succeeded")).toBeInTheDocument();
    });
  });
});
