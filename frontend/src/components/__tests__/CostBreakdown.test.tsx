import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/test-utils";
import { CostBreakdown } from "@/components/evidence/CostBreakdown";
import type { CostBreakdown as CostData } from "@/hooks/useTicketEvidence";

const mockCost: CostData = {
  total_usd: 0.0325,
  input_tokens: 15000,
  output_tokens: 5000,
  model: "claude-sonnet-4-5",
  provider: "anthropic",
};

describe("CostBreakdown", () => {
  it("renders empty state when total is zero", () => {
    const zeroCost: CostData = {
      total_usd: 0,
      input_tokens: 0,
      output_tokens: 0,
      model: "claude-sonnet",
      provider: "anthropic",
    };
    render(<CostBreakdown cost={zeroCost} />);
    expect(screen.getByText("No cost data")).toBeInTheDocument();
  });

  it("renders total cost", () => {
    render(<CostBreakdown cost={mockCost} />);
    expect(screen.getByText("$0.0325")).toBeInTheDocument();
  });

  it("renders Total Cost label", () => {
    render(<CostBreakdown cost={mockCost} />);
    expect(screen.getByText("Total Cost")).toBeInTheDocument();
  });

  it("renders model details", () => {
    render(<CostBreakdown cost={mockCost} />);
    expect(screen.getByText("Model Details")).toBeInTheDocument();
    expect(screen.getByText("claude-sonnet-4-5")).toBeInTheDocument();
    expect(screen.getByText("anthropic")).toBeInTheDocument();
  });

  it("renders token usage section", () => {
    render(<CostBreakdown cost={mockCost} />);
    expect(screen.getByText("Token Usage")).toBeInTheDocument();
    expect(screen.getByText("Input Tokens")).toBeInTheDocument();
    expect(screen.getByText("Output Tokens")).toBeInTheDocument();
    expect(screen.getByText("Total Tokens")).toBeInTheDocument();
  });

  it("formats token counts correctly", () => {
    render(<CostBreakdown cost={mockCost} />);
    // 15000 -> 15.00K, 5000 -> 5.00K, total -> 20.00K
    expect(screen.getByText("15.00K")).toBeInTheDocument();
    expect(screen.getByText("5.00K")).toBeInTheDocument();
    expect(screen.getByText("20.00K")).toBeInTheDocument();
  });

  it("renders cost insights section", () => {
    render(<CostBreakdown cost={mockCost} />);
    expect(
      screen.getByText(/LLM API costs are tracked per ticket/),
    ).toBeInTheDocument();
  });

  it("shows high cost warning when over $1", () => {
    const expensiveCost: CostData = {
      ...mockCost,
      total_usd: 1.5,
    };
    render(<CostBreakdown cost={expensiveCost} />);
    expect(screen.getByText("High cost ticket")).toBeInTheDocument();
  });

  it("does not show high cost warning when under $1", () => {
    render(<CostBreakdown cost={mockCost} />);
    expect(
      screen.queryByText("High cost ticket"),
    ).not.toBeInTheDocument();
  });
});
