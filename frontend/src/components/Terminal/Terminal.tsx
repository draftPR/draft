/**
 * Terminal component wrapping xterm.js.
 *
 * Renders a full terminal emulator with ANSI color support,
 * hyperlinks, auto-fit, and scrollback buffer.
 */

import { useEffect, useRef, useCallback } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";

interface TerminalProps {
  /** Subscribe to output chunks. The callback should return an unsubscribe fn. */
  onReady?: (terminal: XTerm) => void;
  /** Whether terminal is currently active/visible */
  active?: boolean;
  /** Initial content to write when terminal mounts */
  initialContent?: string;
  /** Font size in pixels */
  fontSize?: number;
  /** Scrollback buffer lines */
  scrollback?: number;
}

export function Terminal({
  onReady,
  active = true,
  initialContent,
  fontSize = 13,
  scrollback = 5000,
}: TerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<XTerm | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);

  // Initialize terminal
  useEffect(() => {
    if (!containerRef.current) return;

    const terminal = new XTerm({
      fontSize,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      scrollback,
      cursorBlink: false,
      cursorStyle: "bar",
      disableStdin: true,
      convertEol: true,
      theme: {
        background: "#1a1b26",
        foreground: "#a9b1d6",
        cursor: "#c0caf5",
        selectionBackground: "#33467c",
        black: "#32344a",
        red: "#f7768e",
        green: "#9ece6a",
        yellow: "#e0af68",
        blue: "#7aa2f7",
        magenta: "#ad8ee6",
        cyan: "#449dab",
        white: "#787c99",
        brightBlack: "#444b6a",
        brightRed: "#ff7a93",
        brightGreen: "#b9f27c",
        brightYellow: "#ff9e64",
        brightBlue: "#7da6ff",
        brightMagenta: "#bb9af7",
        brightCyan: "#0db9d7",
        brightWhite: "#acb0d0",
      },
    });

    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();

    terminal.loadAddon(fitAddon);
    terminal.loadAddon(webLinksAddon);

    terminal.open(containerRef.current);
    fitAddon.fit();

    terminalRef.current = terminal;
    fitAddonRef.current = fitAddon;

    if (initialContent) {
      terminal.write(initialContent);
    }

    onReady?.(terminal);

    return () => {
      terminal.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
    };
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle resize
  const handleResize = useCallback(() => {
    if (fitAddonRef.current && active) {
      fitAddonRef.current.fit();
    }
  }, [active]);

  useEffect(() => {
    const observer = new ResizeObserver(handleResize);
    if (containerRef.current) {
      observer.observe(containerRef.current);
    }
    return () => observer.disconnect();
  }, [handleResize]);

  // Re-fit when active changes
  useEffect(() => {
    if (active) {
      handleResize();
    }
  }, [active, handleResize]);

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      style={{ padding: "4px" }}
    />
  );
}
