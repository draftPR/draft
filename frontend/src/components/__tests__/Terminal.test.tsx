import { describe, it, expect, vi } from "vitest";
import { render } from "@/test/test-utils";

// Mock xterm fully - must use class syntax for `new XTerm()`
vi.mock("@xterm/xterm", () => {
  const TerminalMock = vi.fn().mockImplementation(function (this: Record<string, unknown>) {
    this.open = vi.fn();
    this.write = vi.fn();
    this.dispose = vi.fn();
    this.onData = vi.fn();
    this.loadAddon = vi.fn();
    this.options = {};
  });
  return { Terminal: TerminalMock };
});

vi.mock("@xterm/addon-fit", () => {
  const FitAddonMock = vi.fn().mockImplementation(function (this: Record<string, unknown>) {
    this.fit = vi.fn();
    this.dispose = vi.fn();
  });
  return { FitAddon: FitAddonMock };
});

vi.mock("@xterm/addon-web-links", () => {
  const WebLinksAddonMock = vi.fn().mockImplementation(function (this: Record<string, unknown>) {
    this.dispose = vi.fn();
  });
  return { WebLinksAddon: WebLinksAddonMock };
});

vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

import { Terminal } from "@/components/Terminal/Terminal";

describe("Terminal", () => {
  it("renders a container div", () => {
    const { container } = render(<Terminal />);
    const terminalDiv = container.querySelector("div");
    expect(terminalDiv).toBeTruthy();
  });

  it("renders without crashing with all props", () => {
    const onReady = vi.fn();
    const { container } = render(
      <Terminal
        onReady={onReady}
        active={true}
        initialContent="Hello, world!"
        fontSize={14}
        scrollback={10000}
      />,
    );
    expect(container.querySelector("div")).toBeTruthy();
  });

  it("renders without crashing when inactive", () => {
    const { container } = render(<Terminal active={false} />);
    expect(container.querySelector("div")).toBeTruthy();
  });
});
