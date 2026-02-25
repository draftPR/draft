import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { DiffViewer } from "@/components/DiffViewer";

vi.mock("react-diff-viewer-continued", () => ({
  default: () => <div data-testid="diff-viewer" />,
  DiffMethod: { WORDS: "diffWords" },
}));

describe("DiffViewer", () => {
  it("renders empty state when diffPatch is null", () => {
    render(
      <DiffViewer
        diffPatch={null}
        comments={[]}
        onAddComment={vi.fn()}
        onResolveComment={vi.fn()}
        onUnresolveComment={vi.fn()}
      />,
    );
    expect(screen.getByText("No diff content available")).toBeInTheDocument();
  });

  it("renders no diff message for empty string (falsy)", () => {
    render(
      <DiffViewer
        diffPatch=""
        comments={[]}
        onAddComment={vi.fn()}
        onResolveComment={vi.fn()}
        onUnresolveComment={vi.fn()}
      />,
    );
    // Empty string is falsy, so it hits the first null check
    expect(screen.getByText("No diff content available")).toBeInTheDocument();
  });

  it("renders no changes message when patch has no file diffs", () => {
    render(
      <DiffViewer
        diffPatch="some random text with no diff headers"
        comments={[]}
        onAddComment={vi.fn()}
        onResolveComment={vi.fn()}
        onUnresolveComment={vi.fn()}
      />,
    );
    expect(
      screen.getByText("No changes in this revision"),
    ).toBeInTheDocument();
  });

  it("renders file header with file path", () => {
    const patch =
      "diff --git a/src/foo.ts b/src/foo.ts\n--- a/src/foo.ts\n+++ b/src/foo.ts\n@@ -1 +1 @@\n-old\n+new\n";
    render(
      <DiffViewer
        diffPatch={patch}
        comments={[]}
        onAddComment={vi.fn()}
        onResolveComment={vi.fn()}
        onUnresolveComment={vi.fn()}
      />,
    );
    expect(screen.getByText("src/foo.ts")).toBeInTheDocument();
  });

  it("renders the diff viewer component for each file", () => {
    const patch =
      "diff --git a/src/foo.ts b/src/foo.ts\n--- a/src/foo.ts\n+++ b/src/foo.ts\n@@ -1 +1 @@\n-old\n+new\n";
    render(
      <DiffViewer
        diffPatch={patch}
        comments={[]}
        onAddComment={vi.fn()}
        onResolveComment={vi.fn()}
        onUnresolveComment={vi.fn()}
      />,
    );
    expect(screen.getByTestId("diff-viewer")).toBeInTheDocument();
  });

  it("shows hint text when not readOnly", () => {
    const patch =
      "diff --git a/src/bar.ts b/src/bar.ts\n@@ -1 +1 @@\n-a\n+b\n";
    render(
      <DiffViewer
        diffPatch={patch}
        comments={[]}
        onAddComment={vi.fn()}
        onResolveComment={vi.fn()}
        onUnresolveComment={vi.fn()}
        readOnly={false}
      />,
    );
    expect(
      screen.getByText("Click on line numbers to add comments"),
    ).toBeInTheDocument();
  });

  it("does not show hint text in readOnly mode", () => {
    const patch =
      "diff --git a/src/bar.ts b/src/bar.ts\n@@ -1 +1 @@\n-a\n+b\n";
    render(
      <DiffViewer
        diffPatch={patch}
        comments={[]}
        onAddComment={vi.fn()}
        onResolveComment={vi.fn()}
        onUnresolveComment={vi.fn()}
        readOnly={true}
      />,
    );
    expect(
      screen.queryByText("Click on line numbers to add comments"),
    ).not.toBeInTheDocument();
  });
});
