import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/test-utils";
import { MergeStrategyPicker } from "@/components/MergeStrategyPicker";

vi.mock("@/services/api", () => ({
  mergePR: vi.fn(),
}));

describe("MergeStrategyPicker", () => {
  it("renders the PR merge title", () => {
    render(
      <MergeStrategyPicker
        ticketId="ticket-1"
        prNumber={42}
        onMerged={vi.fn()}
      />,
    );
    expect(screen.getByText("Merge PR #42")).toBeInTheDocument();
  });

  it("renders all three strategy options", () => {
    render(
      <MergeStrategyPicker
        ticketId="ticket-1"
        prNumber={42}
        onMerged={vi.fn()}
      />,
    );
    expect(screen.getByText("Squash and merge")).toBeInTheDocument();
    expect(screen.getByText("Merge commit")).toBeInTheDocument();
    expect(screen.getByText("Rebase and merge")).toBeInTheDocument();
  });

  it("renders strategy descriptions", () => {
    render(
      <MergeStrategyPicker
        ticketId="ticket-1"
        prNumber={42}
        onMerged={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Combine all commits into one"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Preserve all commits with merge commit"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Rebase commits onto base branch"),
    ).toBeInTheDocument();
  });

  it("renders the Merge Pull Request button", () => {
    render(
      <MergeStrategyPicker
        ticketId="ticket-1"
        prNumber={42}
        onMerged={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Merge Pull Request"),
    ).toBeInTheDocument();
  });

  it("squash radio is selected by default", () => {
    render(
      <MergeStrategyPicker
        ticketId="ticket-1"
        prNumber={42}
        onMerged={vi.fn()}
      />,
    );
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const squashRadio = radios.find((r) => r.value === "squash");
    expect(squashRadio?.checked).toBe(true);
  });

  it("shows confirm/cancel buttons after clicking Merge Pull Request", async () => {
    render(
      <MergeStrategyPicker
        ticketId="ticket-1"
        prNumber={42}
        onMerged={vi.fn()}
      />,
    );
    const mergeBtn = screen.getByText("Merge Pull Request").closest("button")!;
    await fireEvent.click(mergeBtn);
    await waitFor(() => {
      expect(screen.getByText("Confirm Merge")).toBeInTheDocument();
    });
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });
});
