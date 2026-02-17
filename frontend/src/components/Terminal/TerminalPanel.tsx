/**
 * TerminalPanel -- container for the xterm.js terminal with job selection.
 *
 * Shows a terminal connected to a running job's WebSocket stream.
 * Can be placed in the resizable layout detail panel.
 */

import { useState, useCallback, useRef } from "react";
import type { Terminal as XTerm } from "@xterm/xterm";
import { Terminal } from "./Terminal";
import { useTerminalStream } from "./useTerminalStream";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Trash2, Circle } from "lucide-react";

interface TerminalPanelProps {
  jobId: string | null;
  jobTitle?: string;
}

export function TerminalPanel({ jobId, jobTitle }: TerminalPanelProps) {
  const { status, error, subscribe } = useTerminalStream(jobId);
  const terminalRef = useRef<XTerm | null>(null);
  const [unsubscribe, setUnsubscribe] = useState<(() => void) | null>(null);

  const handleTerminalReady = useCallback(
    (terminal: XTerm) => {
      terminalRef.current = terminal;

      // Clean up previous subscription
      if (unsubscribe) {
        unsubscribe();
      }

      // Subscribe to stream and write to terminal
      const unsub = subscribe((data: string) => {
        terminal.write(data);
      });
      setUnsubscribe(() => unsub);
    },
    [subscribe, unsubscribe],
  );

  const handleClear = useCallback(() => {
    terminalRef.current?.clear();
  }, []);

  const statusColor =
    status === "connected"
      ? "text-green-500"
      : status === "connecting"
        ? "text-yellow-500"
        : status === "error"
          ? "text-red-500"
          : "text-muted-foreground";

  return (
    <div className="h-full flex flex-col">
      {/* Terminal header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-card/50">
        <div className="flex items-center gap-2">
          <Circle className={`h-2.5 w-2.5 fill-current ${statusColor}`} />
          <span className="text-xs font-medium text-muted-foreground">
            {jobTitle || (jobId ? `Job ${jobId.slice(0, 8)}` : "No job")}
          </span>
          {status === "connected" && (
            <Badge
              variant="outline"
              className="text-[10px] px-1.5 py-0 h-4"
            >
              Live
            </Badge>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          className="h-6 w-6 p-0"
          title="Clear terminal"
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>

      {/* Terminal area */}
      <div className="flex-1 min-h-0">
        {jobId ? (
          <Terminal
            onReady={handleTerminalReady}
            active={!!jobId}
            initialContent={
              error
                ? `\x1b[31mError: ${error}\x1b[0m\r\n`
                : `\x1b[36mConnecting to job ${jobId.slice(0, 8)}...\x1b[0m\r\n`
            }
          />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
            Select a running job to view live output
          </div>
        )}
      </div>
    </div>
  );
}
