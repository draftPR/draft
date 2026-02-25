import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { MergeChecklist } from "@/components/MergeChecklist";

const mockChecklistData = {
  id: "mc-1",
  goal_id: "goal-1",
  all_tests_passed: true,
  total_files_changed: 5,
  total_lines_changed: 120,
  total_cost_usd: 0.35,
  budget_exceeded: false,
  code_reviewed: false,
  no_sensitive_data: false,
  rollback_plan_understood: false,
  documentation_updated: false,
  rollback_plan_json: null,
  risk_level: "low",
  ready_to_merge: false,
  merged_at: null,
};

describe("MergeChecklist", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders loading state initially", () => {
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));

    render(<MergeChecklist goalId="goal-1" />);
    // Loading shows a spinner, check container renders
    expect(document.querySelector(".animate-spin")).toBeTruthy();
  });

  it("renders checklist data after loading", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockChecklistData),
    });

    render(<MergeChecklist goalId="goal-1" />);
    await waitFor(() => {
      expect(
        screen.getByText("Merge Readiness Checklist"),
      ).toBeInTheDocument();
    });
  });

  it("renders automated checks section", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockChecklistData),
    });

    render(<MergeChecklist goalId="goal-1" />);
    await waitFor(() => {
      expect(screen.getByText("Automated Checks")).toBeInTheDocument();
    });
    expect(screen.getByText("All Tests Passed")).toBeInTheDocument();
    expect(screen.getByText("Changes Summary")).toBeInTheDocument();
    expect(screen.getByText("Cost Tracking")).toBeInTheDocument();
  });

  it("renders manual verification section", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockChecklistData),
    });

    render(<MergeChecklist goalId="goal-1" />);
    await waitFor(() => {
      expect(
        screen.getByText("Manual Verification"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Code Reviewed")).toBeInTheDocument();
    expect(screen.getByText("No Sensitive Data")).toBeInTheDocument();
    expect(
      screen.getByText("Rollback Plan Understood"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Documentation Updated"),
    ).toBeInTheDocument();
  });

  it("renders Merge All Changes button", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockChecklistData),
    });

    render(<MergeChecklist goalId="goal-1" />);
    await waitFor(() => {
      expect(
        screen.getByText("Merge All Changes"),
      ).toBeInTheDocument();
    });
  });

  it("disables merge button when not ready", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockChecklistData),
    });

    render(<MergeChecklist goalId="goal-1" />);
    await waitFor(() => {
      const mergeBtn = screen
        .getByText("Merge All Changes")
        .closest("button");
      expect(mergeBtn).toBeDisabled();
    });
  });

  it("shows remaining checks count when not ready", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockChecklistData),
    });

    render(<MergeChecklist goalId="goal-1" />);
    await waitFor(() => {
      expect(
        screen.getByText("4 checks remaining"),
      ).toBeInTheDocument();
    });
  });

  it("renders no checklist message on null data", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });

    render(<MergeChecklist goalId="goal-1" />);
    await waitFor(() => {
      expect(
        screen.getByText(/No checklist available yet/),
      ).toBeInTheDocument();
    });
  });
});
