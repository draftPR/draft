import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { RevisionViewer } from "@/components/RevisionViewer";
import type { Revision } from "@/types/api";

// Mock API calls - use literal strings since vi.mock is hoisted
vi.mock("@/services/api", () => ({
  fetchRevision: vi.fn().mockResolvedValue({
    id: "rev-1",
    number: 1,
    status: "open",
    diff_patch: "diff --git a/foo.ts b/foo.ts\n@@ -1 +1 @@\n-old\n+new\n",
    created_at: "2025-01-01T00:00:00Z",
  }),
  fetchRevisionDiff: vi.fn().mockResolvedValue({
    files: [
      { path: "foo.ts", additions: 1, deletions: 1 },
    ],
  }),
  fetchRevisionComments: vi.fn().mockResolvedValue({ comments: [] }),
  addReviewComment: vi.fn(),
  resolveComment: vi.fn(),
  unresolveComment: vi.fn(),
  submitReview: vi.fn(),
}));

// Mock child components that are complex
vi.mock("@/components/DiffViewer", () => ({
  DiffViewer: () => <div data-testid="diff-viewer">DiffViewer</div>,
}));

vi.mock("@/components/ReviewSummaryBox", () => ({
  ReviewSummaryBox: () => <div data-testid="review-summary-box">ReviewSummaryBox</div>,
}));

vi.mock("@/components/RevisionsList", () => ({
  RevisionsList: ({ revisions }: { revisions: unknown[] }) => (
    <div data-testid="revisions-list">{revisions.length} revisions</div>
  ),
}));

const mockRevisions = [
  {
    id: "rev-1",
    ticket_id: "ticket-1",
    number: 1,
    status: "open" as const,
    unresolved_comment_count: 0,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
];

describe("RevisionViewer", () => {
  it("renders the ticket title", () => {
    render(
      <RevisionViewer
        ticketId="ticket-1"
        ticketTitle="Fix login button"
        revisions={mockRevisions as unknown as Revision[]}
        onRevisionUpdated={vi.fn()}
      />,
    );
    expect(screen.getByText("Fix login button")).toBeInTheDocument();
  });

  it("renders the Refresh button", () => {
    render(
      <RevisionViewer
        ticketId="ticket-1"
        ticketTitle="My ticket"
        revisions={mockRevisions as unknown as Revision[]}
        onRevisionUpdated={vi.fn()}
      />,
    );
    expect(screen.getByText("Refresh")).toBeInTheDocument();
  });

  it("renders the Back button when onClose is provided", () => {
    render(
      <RevisionViewer
        ticketId="ticket-1"
        ticketTitle="My ticket"
        revisions={mockRevisions as unknown as Revision[]}
        onRevisionUpdated={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Back")).toBeInTheDocument();
  });

  it("does not render the Back button when onClose is not provided", () => {
    render(
      <RevisionViewer
        ticketId="ticket-1"
        ticketTitle="My ticket"
        revisions={mockRevisions as unknown as Revision[]}
        onRevisionUpdated={vi.fn()}
      />,
    );
    expect(screen.queryByText("Back")).not.toBeInTheDocument();
  });

  it("renders child component placeholders", () => {
    render(
      <RevisionViewer
        ticketId="ticket-1"
        ticketTitle="My ticket"
        revisions={mockRevisions as unknown as Revision[]}
        onRevisionUpdated={vi.fn()}
      />,
    );
    expect(screen.getByTestId("revisions-list")).toBeInTheDocument();
  });

  it("renders Changed Files heading", () => {
    render(
      <RevisionViewer
        ticketId="ticket-1"
        ticketTitle="My ticket"
        revisions={mockRevisions as unknown as Revision[]}
        onRevisionUpdated={vi.fn()}
      />,
    );
    expect(screen.getByText("Changed Files")).toBeInTheDocument();
  });
});
