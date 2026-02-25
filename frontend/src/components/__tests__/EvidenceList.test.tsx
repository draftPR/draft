import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { EvidenceList } from "@/components/EvidenceList";
import type { Evidence } from "@/types/api";

// Mock the API calls used by EvidenceItem
vi.mock("@/services/api", () => ({
  fetchEvidenceStdout: vi.fn().mockResolvedValue("stdout content"),
  fetchEvidenceStderr: vi.fn().mockResolvedValue("stderr content"),
}));

const mockEvidence = [
  {
    id: "ev-1",
    job_id: "job-1",
    command: "npm test",
    exit_code: 0,
    succeeded: true,
    kind: "command_log",
    created_at: "2025-01-15T10:00:00Z",
    updated_at: "2025-01-15T10:00:00Z",
  },
  {
    id: "ev-2",
    job_id: "job-1",
    command: "npm run lint",
    exit_code: 1,
    succeeded: false,
    kind: "command_log",
    created_at: "2025-01-15T10:01:00Z",
    updated_at: "2025-01-15T10:01:00Z",
  },
];

describe("EvidenceList", () => {
  it("renders empty state when no evidence", () => {
    render(<EvidenceList evidence={[]} />);
    expect(screen.getByText("No verification evidence")).toBeInTheDocument();
  });

  it("renders summary counts", () => {
    render(<EvidenceList evidence={mockEvidence as unknown as Evidence[]} />);
    expect(screen.getByText("2 commands total")).toBeInTheDocument();
    expect(screen.getByText("1 passed")).toBeInTheDocument();
    expect(screen.getByText("1 failed")).toBeInTheDocument();
  });

  it("renders evidence commands", () => {
    render(<EvidenceList evidence={mockEvidence as unknown as Evidence[]} />);
    expect(screen.getByText("npm test")).toBeInTheDocument();
    expect(screen.getByText("npm run lint")).toBeInTheDocument();
  });

  it("renders exit codes", () => {
    render(<EvidenceList evidence={mockEvidence as unknown as Evidence[]} />);
    expect(screen.getByText("exit 0")).toBeInTheDocument();
    expect(screen.getByText("exit 1")).toBeInTheDocument();
  });

  it("renders singular 'command' when only one evidence item", () => {
    render(<EvidenceList evidence={[mockEvidence[0]] as unknown as Evidence[]} />);
    expect(screen.getByText("1 command total")).toBeInTheDocument();
  });
});
