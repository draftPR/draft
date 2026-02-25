import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConflictBanner } from "../ConflictBanner";
import type { ConflictStatusResponse, PushStatusResponse } from "@/types/api";

// Mock sonner toast so calls don't throw
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

// Mock the API calls
vi.mock("@/services/api", () => ({
  rebaseTicket: vi.fn(),
  continueRebase: vi.fn(),
  abortConflict: vi.fn(),
  pushTicketBranch: vi.fn(),
  forcePushTicketBranch: vi.fn(),
}));

function makeConflictStatus(
  overrides: Partial<ConflictStatusResponse> = {},
): ConflictStatusResponse {
  return {
    has_conflict: false,
    operation: null,
    conflicted_files: [],
    can_continue: false,
    can_abort: false,
    divergence: null,
    ...overrides,
  };
}

function makePushStatus(
  overrides: Partial<PushStatusResponse> = {},
): PushStatusResponse {
  return {
    ahead: 0,
    behind: 0,
    remote_exists: true,
    needs_push: false,
    ...overrides,
  };
}

describe("ConflictBanner", () => {
  const onResolved = vi.fn();

  it("returns null when there is no conflict, no divergence, and no push needed", () => {
    const { container } = render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus()}
        onResolved={onResolved}
      />,
    );

    expect(container.innerHTML).toBe("");
  });

  it("shows active conflict banner with conflicted files", () => {
    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus({
          has_conflict: true,
          operation: "rebase",
          conflicted_files: ["src/index.ts", "src/app.ts"],
          can_continue: true,
          can_abort: true,
        })}
        onResolved={onResolved}
      />,
    );

    expect(screen.getByText("Rebase conflict")).toBeInTheDocument();
    expect(screen.getByText("2 files with conflicts")).toBeInTheDocument();
    expect(screen.getByText("src/index.ts")).toBeInTheDocument();
    expect(screen.getByText("src/app.ts")).toBeInTheDocument();
  });

  it("shows Continue and Abort buttons when both actions are available", () => {
    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus({
          has_conflict: true,
          operation: "rebase",
          conflicted_files: ["file.ts"],
          can_continue: true,
          can_abort: true,
        })}
        onResolved={onResolved}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Continue/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Abort/i }),
    ).toBeInTheDocument();
  });

  it("hides Continue button when can_continue is false", () => {
    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus({
          has_conflict: true,
          operation: "merge",
          conflicted_files: ["file.ts"],
          can_continue: false,
          can_abort: true,
        })}
        onResolved={onResolved}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /Continue/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Abort/i }),
    ).toBeInTheDocument();
  });

  it("shows divergence banner when branch is behind main", () => {
    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus({
          has_conflict: false,
          divergence: {
            ahead: 2,
            behind: 5,
            diverged: true,
            up_to_date: false,
          },
        })}
        onResolved={onResolved}
      />,
    );

    expect(
      screen.getByText("Branch is 5 commits behind main"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Rebase onto main/i }),
    ).toBeInTheDocument();
  });

  it("shows push banner when needs_push is true and no conflict", () => {
    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus()}
        pushStatus={makePushStatus({ needs_push: true, ahead: 3 })}
        onResolved={onResolved}
      />,
    );

    expect(
      screen.getByText("3 local commits not pushed"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Push$/i }),
    ).toBeInTheDocument();
  });

  it("shows Force Push button when remote exists and needs push", async () => {
    const user = userEvent.setup();

    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus()}
        pushStatus={makePushStatus({
          needs_push: true,
          ahead: 1,
          remote_exists: true,
        })}
        onResolved={onResolved}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Force Push/i }),
    ).toBeInTheDocument();

    // Clicking Force Push shows confirmation
    await user.click(screen.getByRole("button", { name: /Force Push/i }));

    expect(
      screen.getByRole("button", { name: /Confirm/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Cancel/i }),
    ).toBeInTheDocument();
  });

  it("uses singular 'commit' for ahead=1", () => {
    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus()}
        pushStatus={makePushStatus({ needs_push: true, ahead: 1 })}
        onResolved={onResolved}
      />,
    );

    expect(screen.getByText("1 local commit not pushed")).toBeInTheDocument();
  });

  it("uses singular 'file' for single conflicted file", () => {
    render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus({
          has_conflict: true,
          operation: "rebase",
          conflicted_files: ["one.ts"],
          can_continue: false,
          can_abort: true,
        })}
        onResolved={onResolved}
      />,
    );

    expect(screen.getByText("1 file with conflicts")).toBeInTheDocument();
  });

  it("shows correct operation labels", () => {
    const { rerender } = render(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus({
          has_conflict: true,
          operation: "merge",
          conflicted_files: ["f.ts"],
          can_abort: true,
        })}
        onResolved={onResolved}
      />,
    );

    expect(screen.getByText("Merge conflict")).toBeInTheDocument();

    rerender(
      <ConflictBanner
        ticketId="t-1"
        conflictStatus={makeConflictStatus({
          has_conflict: true,
          operation: "cherry_pick",
          conflicted_files: ["f.ts"],
          can_abort: true,
        })}
        onResolved={onResolved}
      />,
    );

    expect(screen.getByText("Cherry-pick conflict")).toBeInTheDocument();
  });
});
