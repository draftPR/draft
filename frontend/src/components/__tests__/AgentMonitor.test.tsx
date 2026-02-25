import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { AgentMonitor } from "@/components/AgentMonitor";

// Mock the useJobStream hook
vi.mock("@/hooks/useJobStream", () => ({
  useJobStream: () => ({
    output: "",
    lines: [],
    isStreaming: false,
    status: "disconnected" as const,
    jobStatus: undefined,
    error: undefined,
  }),
}));

describe("AgentMonitor", () => {
  it("shows empty message when no jobs are provided", () => {
    render(<AgentMonitor jobs={[]} />);
    expect(screen.getByText("No active executions")).toBeInTheDocument();
  });

  it("shows compact empty message when compact is true", () => {
    render(<AgentMonitor jobs={[]} compact />);
    expect(screen.getByText("No active jobs")).toBeInTheDocument();
  });

  it("renders a job card for each provided job", () => {
    const jobs = [
      {
        id: "job-1",
        status: "running" as const,
        ticket: { id: "t1", title: "Fix login bug" },
        executor: "claude",
      },
      {
        id: "job-2",
        status: "queued" as const,
        ticket: { id: "t2", title: "Add tests" },
      },
    ];

    render(<AgentMonitor jobs={jobs} />);

    expect(screen.getByText("Fix login bug")).toBeInTheDocument();
    expect(screen.getByText("Add tests")).toBeInTheDocument();
  });

  it("shows status badge for running job", () => {
    const jobs = [
      {
        id: "job-1",
        status: "running" as const,
        ticket: { id: "t1", title: "Fix login bug" },
      },
    ];

    render(<AgentMonitor jobs={jobs} />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("shows status badge for queued job", () => {
    const jobs = [
      {
        id: "job-1",
        status: "queued" as const,
        ticket: { id: "t1", title: "Setup database" },
      },
    ];

    render(<AgentMonitor jobs={jobs} />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("shows View Logs button when onViewLogs is provided", () => {
    const jobs = [
      {
        id: "job-1",
        status: "running" as const,
        ticket: { id: "t1", title: "Fix bug" },
      },
    ];
    const onViewLogs = vi.fn();

    render(<AgentMonitor jobs={jobs} onViewLogs={onViewLogs} />);
    expect(screen.getByText("View Logs")).toBeInTheDocument();
  });

  it("shows Stop button for running jobs when onStopJob is provided", () => {
    const jobs = [
      {
        id: "job-1",
        status: "running" as const,
        ticket: { id: "t1", title: "Fix bug" },
      },
    ];
    const onStopJob = vi.fn();

    render(<AgentMonitor jobs={jobs} onStopJob={onStopJob} />);
    expect(screen.getByText("Stop")).toBeInTheDocument();
  });

  it("does not show Stop button for queued jobs", () => {
    const jobs = [
      {
        id: "job-1",
        status: "queued" as const,
        ticket: { id: "t1", title: "Fix bug" },
      },
    ];
    const onStopJob = vi.fn();

    render(<AgentMonitor jobs={jobs} onStopJob={onStopJob} />);
    expect(screen.queryByText("Stop")).not.toBeInTheDocument();
  });
});
