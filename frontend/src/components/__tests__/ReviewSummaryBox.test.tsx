import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { ReviewSummaryBox } from "@/components/ReviewSummaryBox";

describe("ReviewSummaryBox", () => {
  it("renders the Reviewed button when hasExistingReview is true", () => {
    render(
      <ReviewSummaryBox
        unresolvedCount={0}
        onSubmitReview={vi.fn()}
        isSubmitting={false}
        hasExistingReview={true}
      />,
    );
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
  });

  it("renders the Review changes button when not reviewed", () => {
    render(
      <ReviewSummaryBox
        unresolvedCount={0}
        onSubmitReview={vi.fn()}
        isSubmitting={false}
        hasExistingReview={false}
      />,
    );
    expect(screen.getByText("Review changes")).toBeInTheDocument();
  });

  it("Reviewed button is disabled when hasExistingReview", () => {
    render(
      <ReviewSummaryBox
        unresolvedCount={0}
        onSubmitReview={vi.fn()}
        isSubmitting={false}
        hasExistingReview={true}
      />,
    );
    const btn = screen.getByText("Reviewed").closest("button");
    expect(btn).toBeDisabled();
  });
});
