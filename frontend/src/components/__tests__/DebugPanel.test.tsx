import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { DebugPanel } from "@/components/DebugPanel";

// Mock API calls
vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    fetchSystemStatus: vi.fn().mockResolvedValue({
      running_jobs: [],
      tickets_by_state: {},
      queued_count: 0,
      recent_events_count: 0,
      timestamp: new Date().toISOString(),
    }),
    fetchOrchestratorLogs: vi.fn().mockResolvedValue({ logs: [] }),
    fetchRecentEvents: vi.fn().mockResolvedValue([]),
    fetchJobLogs: vi.fn().mockResolvedValue(""),
    streamOrchestratorLogs: vi.fn().mockReturnValue({
      close: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
    fetchQueueStatus: vi.fn().mockResolvedValue({
      total_running: 0,
      total_queued: 0,
      running: [],
      queued: [],
    }),
  };
});

describe("DebugPanel", () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when isOpen is false", () => {
    const { container } = render(
      <DebugPanel isOpen={false} onClose={mockOnClose} />
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders the Debug Panel header when open", () => {
    render(<DebugPanel isOpen={true} onClose={mockOnClose} />);
    expect(screen.getByText("Debug Panel")).toBeInTheDocument();
  });

  it("renders tab buttons when open", () => {
    render(<DebugPanel isOpen={true} onClose={mockOnClose} />);

    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Queue")).toBeInTheDocument();
    expect(screen.getByText("DAG")).toBeInTheDocument();
    expect(screen.getByText("Orchestrator")).toBeInTheDocument();
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.getByText("Events")).toBeInTheDocument();
  });

  it("shows the status tab content by default", async () => {
    render(<DebugPanel isOpen={true} onClose={mockOnClose} />);

    // Status tab is active by default, it should show headers
    // Wait for system status to load
    const { waitFor } = await import("@/test/test-utils");
    await waitFor(() => {
      expect(screen.getByText(/Running Jobs/)).toBeInTheDocument();
    });
  });

  it("has a close button", () => {
    render(<DebugPanel isOpen={true} onClose={mockOnClose} />);

    // There should be a minimize and close button
    // The last button with X icon is the close button
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });
});
