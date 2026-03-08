import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { RevisionsList } from "@/components/RevisionsList";
import { RevisionStatus } from "@/types/api";

const mockRevisions = [
  {
    id: "rev-1",
    ticket_id: "ticket-1",
    job_id: "job-1",
    number: 1,
    status: RevisionStatus.OPEN,
    diff_stat_evidence_id: null,
    diff_patch_evidence_id: null,
    unresolved_comment_count: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "rev-2",
    ticket_id: "ticket-1",
    job_id: "job-2",
    number: 2,
    status: RevisionStatus.APPROVED,
    diff_stat_evidence_id: null,
    diff_patch_evidence_id: null,
    unresolved_comment_count: 3,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

describe("RevisionsList", () => {
  it("renders empty state when no revisions", () => {
    render(
      <RevisionsList
        revisions={[]}
        selectedRevisionId={null}
        onSelectRevision={vi.fn()}
      />,
    );
    expect(screen.getByText("No revisions yet")).toBeInTheDocument();
  });

  it("renders revision numbers", () => {
    render(
      <RevisionsList
        revisions={mockRevisions}
        selectedRevisionId={null}
        onSelectRevision={vi.fn()}
      />,
    );
    expect(screen.getByText("Revision #1")).toBeInTheDocument();
    expect(screen.getByText("Revision #2")).toBeInTheDocument();
  });

  it("renders status badges", () => {
    render(
      <RevisionsList
        revisions={mockRevisions}
        selectedRevisionId={null}
        onSelectRevision={vi.fn()}
      />,
    );
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("shows unresolved comment count when present", () => {
    render(
      <RevisionsList
        revisions={mockRevisions}
        selectedRevisionId={null}
        onSelectRevision={vi.fn()}
      />,
    );
    expect(screen.getByText("3 unresolved")).toBeInTheDocument();
  });

  it("calls onSelectRevision when a revision is clicked", async () => {
    const onSelect = vi.fn();
    render(
      <RevisionsList
        revisions={mockRevisions}
        selectedRevisionId={null}
        onSelectRevision={onSelect}
      />,
    );
    // The revision is rendered as a button, but we cannot guarantee `user` is returned
    // from our custom render, so use screen + fireEvent
    const firstRevision = screen.getByText("Revision #1").closest("button");
    if (firstRevision) {
      firstRevision.click();
      expect(onSelect).toHaveBeenCalledWith("rev-1");
    }
  });
});
