import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import userEvent from "@testing-library/user-event";
import { ReflectionDialog } from "../ReflectionDialog";

describe("ReflectionDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    goalId: "goal-1",
    goalTitle: "My Test Goal",
    onPrioritiesUpdated: vi.fn(),
  };

  it("renders dialog content when open", () => {
    render(<ReflectionDialog {...defaultProps} />);

    expect(screen.getByText("AI Reflection")).toBeInTheDocument();
    expect(
      screen.getByText(/Analyze proposed tickets for "My Test Goal"/),
    ).toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(<ReflectionDialog {...defaultProps} open={false} />);

    expect(screen.queryByText("AI Reflection")).not.toBeInTheDocument();
  });

  it("shows initial state with Run Reflection button", () => {
    render(<ReflectionDialog {...defaultProps} />);

    expect(
      screen.getByRole("button", { name: /Run Reflection/ }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        /Run AI reflection to evaluate ticket quality/,
      ),
    ).toBeInTheDocument();
  });

  it("includes the goal title in the description", () => {
    render(
      <ReflectionDialog {...defaultProps} goalTitle="Build a spaceship" />,
    );

    expect(
      screen.getByText(/Analyze proposed tickets for "Build a spaceship"/),
    ).toBeInTheDocument();
  });

  it("shows loading state when Run Reflection is clicked", async () => {
    const user = userEvent.setup();

    render(<ReflectionDialog {...defaultProps} />);

    await user.click(
      screen.getByRole("button", { name: /Run Reflection/ }),
    );

    // After clicking, it should show analyzing state
    expect(screen.getByText("Analyzing tickets...")).toBeInTheDocument();
  });
});
