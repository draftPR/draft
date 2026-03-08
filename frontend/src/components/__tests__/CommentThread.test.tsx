import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { CommentThread } from "@/components/CommentThread";
import type { ReviewComment } from "@/types/api";

const baseComment: ReviewComment = {
  id: "comment-1",
  revision_id: "rev-1",
  file_path: "src/app.ts",
  line_number: 42,
  anchor: "src/app.ts:42",
  body: "This function needs error handling",
  author_type: "human",
  resolved: false,
  line_content: "function doStuff() {",
  created_at: new Date().toISOString(),
};

describe("CommentThread", () => {
  it("renders the comment body", () => {
    render(
      <CommentThread
        comment={baseComment}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(
      screen.getByText("This function needs error handling"),
    ).toBeInTheDocument();
  });

  it("renders the author label for human type", () => {
    render(
      <CommentThread
        comment={baseComment}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(screen.getByText("Reviewer")).toBeInTheDocument();
  });

  it("renders the author label for agent type", () => {
    render(
      <CommentThread
        comment={{ ...baseComment, author_type: "agent" }}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(screen.getByText("Agent")).toBeInTheDocument();
  });

  it("renders the author label for system type", () => {
    render(
      <CommentThread
        comment={{ ...baseComment, author_type: "system" }}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(screen.getByText("System")).toBeInTheDocument();
  });

  it("renders the Resolve button when not resolved", () => {
    render(
      <CommentThread
        comment={baseComment}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(screen.getByText("Resolve")).toBeInTheDocument();
  });

  it("renders the Unresolve button when resolved", () => {
    render(
      <CommentThread
        comment={{ ...baseComment, resolved: true }}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(screen.getByText("Unresolve")).toBeInTheDocument();
  });

  it("shows Resolved badge when comment is resolved", () => {
    render(
      <CommentThread
        comment={{ ...baseComment, resolved: true }}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(screen.getByText("Resolved")).toBeInTheDocument();
  });

  it("renders line content when present", () => {
    render(
      <CommentThread
        comment={baseComment}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
      />,
    );
    expect(screen.getByText("function doStuff() {")).toBeInTheDocument();
    expect(screen.getByText("src/app.ts:42")).toBeInTheDocument();
  });

  it("does not render resolve buttons in readOnly mode", () => {
    render(
      <CommentThread
        comment={baseComment}
        onResolve={vi.fn()}
        onUnresolve={vi.fn()}
        readOnly
      />,
    );
    expect(screen.queryByText("Resolve")).not.toBeInTheDocument();
  });
});
