import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { TicketDAGView } from "@/components/TicketDAGView";

vi.mock("@/config", () => ({
  config: { backendBaseUrl: "http://localhost:8000" },
}));

const mockTickets = [
  {
    id: "t-1",
    title: "First ticket",
    state: "planned",
    priority: 80,
    blocked_by_ticket_id: null,
  },
  {
    id: "t-2",
    title: "Second ticket",
    state: "executing",
    priority: 60,
    blocked_by_ticket_id: "t-1",
  },
];

describe("TicketDAGView", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders loading state initially", () => {
    // Never resolve the fetch
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}));

    render(<TicketDAGView />);
    // The loading spinner should appear
    // It uses Loader2 spinner without text, just checking the DOM renders
    expect(document.querySelector(".animate-spin")).toBeTruthy();
  });

  it("renders error state on fetch failure", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Network error"));

    render(<TicketDAGView />);
    await waitFor(() => {
      expect(screen.getByText("Failed to load DAG")).toBeInTheDocument();
    });
  });

  it("renders empty state when no tickets", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ columns: [] }),
    });

    render(<TicketDAGView />);
    await waitFor(() => {
      expect(
        screen.getByText("No tickets to visualize"),
      ).toBeInTheDocument();
    });
  });

  it("renders DAG with tickets", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          columns: [{ tickets: mockTickets }],
        }),
    });

    render(<TicketDAGView />);
    await waitFor(() => {
      expect(
        screen.getByText("Ticket Dependency Graph"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Tickets: 2")).toBeInTheDocument();
    expect(screen.getByText("Dependencies: 1")).toBeInTheDocument();
  });

  it("renders ticket titles in SVG nodes (truncated)", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          columns: [{ tickets: mockTickets }],
        }),
    });

    render(<TicketDAGView />);
    await waitFor(() => {
      expect(screen.getByText("First ticket")).toBeInTheDocument();
    });
    expect(screen.getByText("Second ticket")).toBeInTheDocument();
  });
});
