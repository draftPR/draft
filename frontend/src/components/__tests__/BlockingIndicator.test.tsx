import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BlockingIndicator } from "../BlockingIndicator";

describe("BlockingIndicator", () => {
  const defaultProps = {
    blockedByTicketId: "ticket-123",
    blockedByTicketTitle: "Fix auth flow",
  };

  it("shows blocked-by text with the ticket title", () => {
    render(<BlockingIndicator {...defaultProps} />);

    expect(screen.getByText("Blocked by: Fix auth flow")).toBeInTheDocument();
  });

  it("shows compact mode with truncated text", () => {
    render(
      <BlockingIndicator
        blockedByTicketId="ticket-123"
        blockedByTicketTitle="Fix authentication flow bugs"
        compact
      />,
    );

    // Compact mode truncates to 15 chars and adds "..."
    expect(screen.getByText(/Fix authenticat\.\.\./)).toBeInTheDocument();
  });

  it("calls onNavigateToBlocker with the ticket ID when clicked", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();

    render(
      <BlockingIndicator
        {...defaultProps}
        onNavigateToBlocker={onNavigate}
      />,
    );

    await user.click(screen.getByText("Blocked by: Fix auth flow"));
    expect(onNavigate).toHaveBeenCalledWith("ticket-123");
  });

  it("does not call anything when clicked without onNavigateToBlocker", async () => {
    const user = userEvent.setup();

    render(<BlockingIndicator {...defaultProps} />);

    // Should not throw when clicked
    await user.click(screen.getByText("Blocked by: Fix auth flow"));
  });

  it("shows fallback 'Unknown ticket' when no title is provided", () => {
    render(
      <BlockingIndicator
        blockedByTicketId="ticket-456"
        blockedByTicketTitle={null}
      />,
    );

    expect(screen.getByText("Blocked by: Unknown ticket")).toBeInTheDocument();
  });

  it("shows ExternalLink icon only when onNavigateToBlocker is provided", () => {
    const { rerender, container } = render(
      <BlockingIndicator {...defaultProps} />,
    );

    // Without onNavigateToBlocker: no external-link icon beyond the Lock icon
    // Lock icon is always there; ExternalLink is conditional
    const svgsBefore = container.querySelectorAll("svg");
    const svgCountWithout = svgsBefore.length;

    rerender(
      <BlockingIndicator {...defaultProps} onNavigateToBlocker={vi.fn()} />,
    );

    const svgsAfter = container.querySelectorAll("svg");
    // With onNavigateToBlocker, there should be one more SVG (ExternalLink)
    expect(svgsAfter.length).toBe(svgCountWithout + 1);
  });

  it("has click-to-view tooltip when onNavigateToBlocker is provided", () => {
    render(
      <BlockingIndicator {...defaultProps} onNavigateToBlocker={vi.fn()} />,
    );

    const element = screen.getByTitle("Click to view blocker ticket");
    expect(element).toBeInTheDocument();
  });
});
