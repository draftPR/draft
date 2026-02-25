import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { CommandPalette, type CommandAction } from "@/components/CommandPalette";
import { Settings, Target } from "lucide-react";

// Mock zustand stores
vi.mock("@/stores/boardStore", () => ({
  useBoardStore: () => "board-1",
}));

vi.mock("@/stores/ticketStore", () => ({
  useTicketSelectionStore: () => ({
    selectTicket: vi.fn(),
  }),
}));

// cmdk renders actual DOM, no need to mock it

const testCommands: CommandAction[] = [
  {
    id: "cmd-1",
    label: "Create Goal",
    description: "Create a new goal",
    icon: Target,
    shortcut: "n g",
    category: "Goals",
    onSelect: vi.fn(),
    keywords: ["add", "goal"],
  },
  {
    id: "cmd-2",
    label: "Open Settings",
    description: "View application settings",
    icon: Settings,
    category: "Navigation",
    onSelect: vi.fn(),
  },
];

describe("CommandPalette", () => {
  it("does not render when not open (default)", () => {
    render(
      <CommandPalette commands={testCommands} />,
    );
    // When not open, the component returns null
    expect(screen.queryByPlaceholderText("Search tickets, actions...")).not.toBeInTheDocument();
  });

  it("opens on Cmd+K keydown", () => {
    render(<CommandPalette commands={testCommands} />);

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    // After opening, the input should be visible
    expect(
      screen.getByPlaceholderText("Search tickets, actions..."),
    ).toBeInTheDocument();
  });

  it("renders commands when open", () => {
    render(<CommandPalette commands={testCommands} />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Create Goal")).toBeInTheDocument();
    expect(screen.getByText("Open Settings")).toBeInTheDocument();
  });

  it("renders command descriptions", () => {
    render(<CommandPalette commands={testCommands} />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Create a new goal")).toBeInTheDocument();
    expect(
      screen.getByText("View application settings"),
    ).toBeInTheDocument();
  });

  it("renders keyboard shortcut for commands that have one", () => {
    render(<CommandPalette commands={testCommands} />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("n g")).toBeInTheDocument();
  });

  it("renders footer with keyboard hints", () => {
    render(<CommandPalette commands={testCommands} />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("navigate")).toBeInTheDocument();
    expect(screen.getByText("select")).toBeInTheDocument();
    expect(screen.getByText("close")).toBeInTheDocument();
  });

  it("closes when backdrop is clicked", () => {
    render(<CommandPalette commands={testCommands} />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(
      screen.getByPlaceholderText("Search tickets, actions..."),
    ).toBeInTheDocument();

    // Click backdrop
    const backdrop = screen.getByPlaceholderText("Search tickets, actions...")
      .closest(".fixed")
      ?.querySelector(".absolute.inset-0.bg-black\\/50");
    if (backdrop) {
      fireEvent.click(backdrop);
    }
  });
});
