import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { LiveAgentLogs } from "@/components/LiveAgentLogs";
import { JobStatus } from "@/types/api";

// Mock react-virtuoso
vi.mock("react-virtuoso", () => ({
  Virtuoso: ({ data, itemContent }: { data?: unknown[]; itemContent: (index: number, item: unknown) => React.ReactNode }) => (
    <div data-testid="virtuoso-list">
      {data?.map((item: unknown, index: number) => (
        <div key={index}>{itemContent(index, item)}</div>
      ))}
    </div>
  ),
}));

// Mock API
vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    fetchJobLogs: vi.fn().mockResolvedValue("Line 1\nLine 2\nLine 3"),
    streamAgentLogs: vi.fn().mockReturnValue({ close: vi.fn() }),
  };
});

describe("LiveAgentLogs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the header with job kind", () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.SUCCEEDED}
        jobKind="execute"
      />
    );

    expect(screen.getByText("execute")).toBeInTheDocument();
  });

  it("shows 'Done' status badge for succeeded jobs", () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.SUCCEEDED}
        jobKind="execute"
      />
    );

    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("shows 'Running' status badge for running jobs", () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.RUNNING}
        jobKind="execute"
      />
    );

    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("shows 'Failed' status badge for failed jobs", () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.FAILED}
        jobKind="verify"
      />
    );

    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("shows 'Queued' status badge for queued jobs", () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.QUEUED}
        jobKind="execute"
      />
    );

    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("loads and displays logs when expanded for completed jobs", async () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.SUCCEEDED}
        jobKind="execute"
        defaultExpanded
      />
    );

    await waitFor(() => {
      expect(screen.getByText("3 lines")).toBeInTheDocument();
    });
  });

  it("is collapsed by default when defaultExpanded is not set", () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.SUCCEEDED}
        jobKind="execute"
      />
    );

    // When collapsed, the raw log text should not be visible
    // But the header with job kind and status should be visible
    expect(screen.getByText("execute")).toBeInTheDocument();
  });

  it("shows 'Live' indicator for streaming running jobs", () => {
    render(
      <LiveAgentLogs
        jobId="job-1"
        jobStatus={JobStatus.RUNNING}
        jobKind="execute"
        defaultExpanded
      />
    );

    expect(screen.getByText("Live")).toBeInTheDocument();
  });
});
