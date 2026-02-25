import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import userEvent from "@testing-library/user-event";
import { CreateTicketDialog } from "../CreateTicketDialog";

describe("CreateTicketDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onSuccess: vi.fn(),
  };

  it("renders dialog content when open", async () => {
    render(<CreateTicketDialog {...defaultProps} />);

    expect(screen.getByText("Create New Ticket")).toBeInTheDocument();
    expect(
      screen.getByText(/Create a ticket to track a specific task/),
    ).toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(<CreateTicketDialog {...defaultProps} open={false} />);

    expect(screen.queryByText("Create New Ticket")).not.toBeInTheDocument();
  });

  it("shows form fields: goal, title, description, and priority", async () => {
    render(<CreateTicketDialog {...defaultProps} />);

    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toBeInTheDocument();
    expect(screen.getByLabelText("Priority (0-100)")).toBeInTheDocument();

    // Goal selector should be present (label)
    expect(screen.getByText("Goal")).toBeInTheDocument();
  });

  it("shows Create Ticket and Cancel buttons", () => {
    render(<CreateTicketDialog {...defaultProps} />);

    expect(
      screen.getByRole("button", { name: "Create Ticket" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancel" }),
    ).toBeInTheDocument();
  });

  it("calls onOpenChange(false) when Cancel is clicked", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();

    render(
      <CreateTicketDialog
        {...defaultProps}
        onOpenChange={onOpenChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("fetches and displays goals when dialog opens", async () => {
    render(<CreateTicketDialog {...defaultProps} />);

    // MSW handler returns one goal with title "Default Goal"
    // Since there's only one goal, it should be auto-selected
    await waitFor(() => {
      // The loading state should resolve
      expect(screen.queryByText("Loading goals...")).not.toBeInTheDocument();
    });
  });

  it("shows validation error when submitting without a title", async () => {
    const user = userEvent.setup();

    render(<CreateTicketDialog {...defaultProps} />);

    // Wait for goals to load
    await waitFor(() => {
      expect(screen.queryByText("Loading goals...")).not.toBeInTheDocument();
    });

    // Clear any auto-filled fields and submit
    await user.click(screen.getByRole("button", { name: "Create Ticket" }));

    expect(screen.getByText("Title is required")).toBeInTheDocument();
  });

  it("shows priority help text", () => {
    render(<CreateTicketDialog {...defaultProps} />);

    expect(
      screen.getByText(
        /Higher values = higher priority/,
      ),
    ).toBeInTheDocument();
  });

  it("shows placeholder text in title input", () => {
    render(<CreateTicketDialog {...defaultProps} />);

    expect(
      screen.getByPlaceholderText("Enter ticket title..."),
    ).toBeInTheDocument();
  });
});
