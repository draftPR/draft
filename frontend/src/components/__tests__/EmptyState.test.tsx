import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState } from "../EmptyState";
import { Inbox } from "lucide-react";

describe("EmptyState", () => {
  it("renders icon, title, and description", () => {
    render(
      <EmptyState
        icon={Inbox}
        title="No tickets"
        description="Create a ticket to get started"
      />,
    );

    expect(screen.getByText("No tickets")).toBeInTheDocument();
    expect(
      screen.getByText("Create a ticket to get started"),
    ).toBeInTheDocument();
  });

  it("renders action button when provided", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <EmptyState
        icon={Inbox}
        title="No tickets"
        action={{ label: "Create Ticket", onClick }}
      />,
    );

    const button = screen.getByRole("button", { name: "Create Ticket" });
    expect(button).toBeInTheDocument();

    await user.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("does not render action button when not provided", () => {
    render(<EmptyState icon={Inbox} title="No tickets" />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders compact mode without description", () => {
    render(
      <EmptyState
        icon={Inbox}
        title="No tickets"
        description="This should not appear"
        compact
      />,
    );

    expect(screen.getByText("No tickets")).toBeInTheDocument();
    // In compact mode, description is not rendered regardless of prop
    expect(
      screen.queryByText("This should not appear"),
    ).not.toBeInTheDocument();
  });

  it("hides description when not provided", () => {
    const { container } = render(
      <EmptyState icon={Inbox} title="No tickets" />,
    );

    // Title is present
    expect(screen.getByText("No tickets")).toBeInTheDocument();
    // No second <p> for description
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs).toHaveLength(1);
  });

  it("does not render action button in compact mode", () => {
    const onClick = vi.fn();

    render(
      <EmptyState
        icon={Inbox}
        title="No tickets"
        action={{ label: "Create", onClick }}
        compact
      />,
    );

    // Compact mode does not include action buttons
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
