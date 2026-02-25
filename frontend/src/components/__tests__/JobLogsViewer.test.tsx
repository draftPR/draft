import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { JobLogsViewer } from "@/components/JobLogsViewer";

// Mock API -- use a variable we can control per test
const mockFetchJobLogs = vi.fn().mockResolvedValue("Build started\nCompiling...\nBuild succeeded");

vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    fetchJobLogs: (...args: unknown[]) => mockFetchJobLogs(...args),
  };
});

describe("JobLogsViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchJobLogs.mockResolvedValue("Build started\nCompiling...\nBuild succeeded");
  });

  it("renders the ticket title in the header", () => {
    render(
      <JobLogsViewer jobId="job-1" ticketTitle="Fix login form" />
    );
    expect(screen.getByText("Fix login form")).toBeInTheDocument();
  });

  it("shows 'Live' indicator when job is running", () => {
    render(
      <JobLogsViewer
        jobId="job-1"
        ticketTitle="Fix login form"
        isRunning
      />
    );
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("does not show Live indicator when job is not running", () => {
    render(
      <JobLogsViewer jobId="job-1" ticketTitle="Fix login form" />
    );
    expect(screen.queryByText("Live")).not.toBeInTheDocument();
  });

  it("loads and displays log content", async () => {
    render(
      <JobLogsViewer jobId="job-1" ticketTitle="Fix login form" />
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Build started/)
      ).toBeInTheDocument();
    });
  });

  it("shows line count", async () => {
    render(
      <JobLogsViewer jobId="job-1" ticketTitle="Fix login form" />
    );

    await waitFor(() => {
      expect(screen.getByText("3 lines")).toBeInTheDocument();
    });
  });

  it("shows loading spinner before logs arrive", () => {
    mockFetchJobLogs.mockReturnValue(new Promise(() => {})); // never resolves

    render(
      <JobLogsViewer jobId="job-2" ticketTitle="Pending job" />
    );

    // The loading spinner should be visible (Loader2 with animate-spin)
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });

  it("shows error message when log fetch fails", async () => {
    mockFetchJobLogs.mockRejectedValue(new Error("Log file not found"));

    render(
      <JobLogsViewer jobId="job-3" ticketTitle="Failed job" />
    );

    await waitFor(() => {
      expect(screen.getByText("Log file not found")).toBeInTheDocument();
    });
  });
});
