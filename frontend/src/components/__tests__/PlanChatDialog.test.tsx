import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import userEvent from "@testing-library/user-event";
import { PlanChatDialog } from "../PlanChatDialog";
import { applyPlan, planChat } from "@/services/api";

vi.mock("@/contexts/BoardContext", () => ({
  useBoard: () => ({ currentBoard: { id: "board-1", name: "Test Board" } }),
}));

vi.mock("@/services/api", () => ({
  fetchGoals: vi.fn().mockResolvedValue({ goals: [], total: 0 }),
  planChat: vi.fn().mockResolvedValue({
    reply: "Drafted 1 goal.",
    goals: [
      {
        title: "CSV export",
        description: "Export boards",
        existing_goal_id: null,
        tickets: [
          {
            title: "Export endpoint",
            description: "",
            priority_bucket: "P1",
            blocked_by: null,
          },
          {
            title: "Export button",
            description: "",
            priority_bucket: "P2",
            blocked_by: "Export endpoint",
          },
        ],
      },
    ],
  }),
  applyPlan: vi
    .fn()
    .mockResolvedValue({
      goal_ids: ["g1"],
      goals_created: 1,
      tickets_created: 1,
    }),
}));

describe("PlanChatDialog", () => {
  it("chats notes into a plan, applies edits, and creates it", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    render(
      <PlanChatDialog open onOpenChange={vi.fn()} onSuccess={onSuccess} />
    );

    await user.type(
      screen.getByLabelText("Message"),
      "notes: add CSV export{Enter}"
    );

    expect(await screen.findByText("Drafted 1 goal.")).toBeInTheDocument();
    expect(planChat).toHaveBeenCalledWith(
      "board-1",
      [{ role: "user", content: "notes: add CSV export" }],
      []
    );
    expect(screen.getByDisplayValue("Export button")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Priority P1, click to change"));
    await user.click(screen.getByLabelText("Remove ticket Export button"));
    await user.click(
      screen.getByRole("button", { name: /Create 1 new goal · 1 ticket/ })
    );

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(["g1"]));
    const [, goals] = vi.mocked(applyPlan).mock.calls[0];
    expect(goals[0].tickets).toEqual([
      expect.objectContaining({
        title: "Export endpoint",
        priority_bucket: "P2",
      }),
    ]);
  });
});
