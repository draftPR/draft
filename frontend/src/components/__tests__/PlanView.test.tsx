import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/test-utils";
import { PlanView } from "@/components/evidence/PlanView";
import type { TicketPlan } from "@/hooks/useTicketEvidence";

const mockPlan: TicketPlan = {
  description: "Fix the calculator division function to handle edge cases",
  approach: "Update the divide function and add comprehensive tests",
  files_to_modify: ["src/utils/calculator.ts", "tests/calculator.test.ts"],
  estimated_complexity: "medium",
};

describe("PlanView", () => {
  it("renders the Agent's Plan title", () => {
    render(<PlanView plan={mockPlan} />);
    expect(screen.getByText("Agent's Plan")).toBeInTheDocument();
  });

  it("renders the complexity badge", () => {
    render(<PlanView plan={mockPlan} />);
    expect(screen.getByText("medium complexity")).toBeInTheDocument();
  });

  it("renders the description", () => {
    render(<PlanView plan={mockPlan} />);
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Fix the calculator division function to handle edge cases",
      ),
    ).toBeInTheDocument();
  });

  it("renders the approach", () => {
    render(<PlanView plan={mockPlan} />);
    expect(screen.getByText("Approach")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Update the divide function and add comprehensive tests",
      ),
    ).toBeInTheDocument();
  });

  it("renders files to modify", () => {
    render(<PlanView plan={mockPlan} />);
    expect(screen.getByText("Files to Modify (2)")).toBeInTheDocument();
    expect(
      screen.getByText("src/utils/calculator.ts"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("tests/calculator.test.ts"),
    ).toBeInTheDocument();
  });

  it("does not render files section when no files to modify", () => {
    const planNoFiles: TicketPlan = {
      ...mockPlan,
      files_to_modify: [],
    };
    render(<PlanView plan={planNoFiles} />);
    expect(screen.queryByText(/Files to Modify/)).not.toBeInTheDocument();
  });

  it("renders the info callout about comparing plans", () => {
    render(<PlanView plan={mockPlan} />);
    expect(
      screen.getByText(/This is what the agent planned to do/),
    ).toBeInTheDocument();
  });

  it("renders low complexity badge for low complexity plan", () => {
    const lowPlan: TicketPlan = {
      ...mockPlan,
      estimated_complexity: "low",
    };
    render(<PlanView plan={lowPlan} />);
    expect(screen.getByText("low complexity")).toBeInTheDocument();
  });

  it("renders high complexity badge for high complexity plan", () => {
    const highPlan: TicketPlan = {
      ...mockPlan,
      estimated_complexity: "high",
    };
    render(<PlanView plan={highPlan} />);
    expect(screen.getByText("high complexity")).toBeInTheDocument();
  });
});
