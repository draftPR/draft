import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { FileTree } from "@/components/FileTree/FileTree";

const mockTree = {
  name: "root",
  path: "/",
  is_dir: true,
  children: [
    {
      name: "src",
      path: "/src",
      is_dir: true,
      children: [
        {
          name: "app.ts",
          path: "/src/app.ts",
          is_dir: false,
          size: 1024,
        },
        {
          name: "utils.py",
          path: "/src/utils.py",
          is_dir: false,
          size: 512,
        },
      ],
    },
    {
      name: "README.md",
      path: "/README.md",
      is_dir: false,
      size: 256,
    },
  ],
};

describe("FileTree", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders loading state initially", () => {
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}));

    render(<FileTree ticketId="ticket-1" />);
    expect(screen.getByText("Loading files...")).toBeInTheDocument();
  });

  it("renders error state on fetch failure", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    });

    render(<FileTree ticketId="ticket-1" />);
    await waitFor(() => {
      expect(
        screen.getByText(/Failed to load file tree: 404/),
      ).toBeInTheDocument();
    });
  });

  it("renders no worktree message when tree is null", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(null),
    });

    render(<FileTree ticketId="ticket-1" />);
    await waitFor(() => {
      expect(
        screen.getByText("No worktree found for this ticket."),
      ).toBeInTheDocument();
    });
  });

  it("renders file tree with directories and files", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockTree),
    });

    render(<FileTree ticketId="ticket-1" />);
    await waitFor(() => {
      expect(screen.getByText("src")).toBeInTheDocument();
    });
    expect(screen.getByText("README.md")).toBeInTheDocument();
  });

  it("expands directories at depth 0 by default", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockTree),
    });

    render(<FileTree ticketId="ticket-1" />);
    await waitFor(() => {
      // Children of root.children (src dir) start at depth 0, which is < 1, so auto-expanded
      expect(screen.getByText("app.ts")).toBeInTheDocument();
      expect(screen.getByText("utils.py")).toBeInTheDocument();
    });
  });

  it("calls onFileSelect when a file is clicked", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockTree),
    });

    const onFileSelect = vi.fn();
    render(<FileTree ticketId="ticket-1" onFileSelect={onFileSelect} />);
    await waitFor(() => {
      expect(screen.getByText("app.ts")).toBeInTheDocument();
    });

    screen.getByText("app.ts").click();
    expect(onFileSelect).toHaveBeenCalledWith("/src/app.ts");
  });

  it("sorts directories before files", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockTree),
    });

    render(<FileTree ticketId="ticket-1" />);
    await waitFor(() => {
      const buttons = screen.getAllByRole("button");
      const names = buttons.map((b) => b.textContent?.trim());
      // "src" directory should come before "README.md" file
      const srcIdx = names.indexOf("src");
      const readmeIdx = names.indexOf("README.md");
      expect(srcIdx).toBeLessThan(readmeIdx);
    });
  });
});
