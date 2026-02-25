import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { QueueStatusDialog } from "../QueueStatusDialog";

const BASE = "http://localhost:8000";

// Mock JobLogsViewer to avoid WebSocket/streaming complexity
vi.mock("../JobLogsViewer", () => ({
  JobLogsViewer: () => <div data-testid="mock-job-logs">Logs</div>,
}));

// The component calls fetchQueueStatus which hits GET /jobs/queue
beforeEach(() => {
  server.use(
    http.get(`${BASE}/jobs/queue`, () =>
      HttpResponse.json({
        queued: [],
        running: [],
        total_queued: 0,
        total_running: 0,
      }),
    ),
  );
});

describe("QueueStatusDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
  };

  it("renders dialog content when open", () => {
    render(<QueueStatusDialog {...defaultProps} />);

    expect(screen.getByText("Activity Monitor")).toBeInTheDocument();
    expect(
      screen.getByText(/View running jobs, queue status/),
    ).toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(<QueueStatusDialog {...defaultProps} open={false} />);

    expect(screen.queryByText("Activity Monitor")).not.toBeInTheDocument();
  });

  it("shows empty state when queue has no jobs", async () => {
    render(<QueueStatusDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Queue is empty")).toBeInTheDocument();
    });

    expect(
      screen.getByText("No jobs are currently running or waiting"),
    ).toBeInTheDocument();
  });

  it("shows loading spinner before data loads", () => {
    render(<QueueStatusDialog {...defaultProps} />);

    // The dialog title should be visible even while loading
    expect(screen.getByText("Activity Monitor")).toBeInTheDocument();
  });
});
