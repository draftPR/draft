import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/test-utils";
import { TestResults } from "@/components/evidence/TestResults";
import type { TestResult } from "@/hooks/useTicketEvidence";

const mockResults: TestResult[] = [
  {
    name: "test_add",
    status: "passed",
    duration_ms: 120,
  },
  {
    name: "test_divide",
    status: "failed",
    duration_ms: 450,
    error: "AssertionError: expected 4 but got 5",
  },
  {
    name: "test_multiply",
    status: "skipped",
    duration_ms: 0,
  },
];

describe("TestResults", () => {
  it("renders empty state when no results", () => {
    render(<TestResults results={[]} />);
    expect(screen.getByText("No test results")).toBeInTheDocument();
  });

  it("renders the test summary card", () => {
    render(<TestResults results={mockResults} />);
    expect(screen.getByText("Test Summary")).toBeInTheDocument();
  });

  it("renders total count", () => {
    render(<TestResults results={mockResults} />);
    // The total is rendered as a large bold number
    const totals = screen.getAllByText("3");
    expect(totals.length).toBeGreaterThan(0);
  });

  it("renders passed, failed, skipped counts", () => {
    render(<TestResults results={mockResults} />);
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Skipped")).toBeInTheDocument();
  });

  it("renders individual test names", () => {
    render(<TestResults results={mockResults} />);
    expect(screen.getByText("test_add")).toBeInTheDocument();
    expect(screen.getByText("test_divide")).toBeInTheDocument();
    expect(screen.getByText("test_multiply")).toBeInTheDocument();
  });

  it("renders duration for each test", () => {
    render(<TestResults results={mockResults} />);
    expect(screen.getByText("0.12s")).toBeInTheDocument();
    expect(screen.getByText("0.45s")).toBeInTheDocument();
  });

  it("renders status badges", () => {
    render(<TestResults results={mockResults} />);
    expect(screen.getByText("passed")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("skipped")).toBeInTheDocument();
  });

  it("renders failure warning when tests fail", () => {
    render(<TestResults results={mockResults} />);
    expect(screen.getByText("1 test failed")).toBeInTheDocument();
  });

  it("renders success message when all tests pass", () => {
    const allPassed: TestResult[] = [
      { name: "test_a", status: "passed", duration_ms: 100 },
      { name: "test_b", status: "passed", duration_ms: 200 },
    ];
    render(<TestResults results={allPassed} />);
    expect(screen.getByText(/All tests passed!/)).toBeInTheDocument();
  });

  it("renders total duration", () => {
    render(<TestResults results={mockResults} />);
    // Total: 120 + 450 + 0 = 570ms = 0.57s
    expect(screen.getByText("0.57s")).toBeInTheDocument();
  });
});
