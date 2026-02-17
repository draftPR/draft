/**
 * Main router component for displaying different types of log entries
 */

import type { NormalizedLogEntry } from "@/types/logs";
import { ThinkingCard } from "./ThinkingCard";
import { FileChangeRenderer } from "./FileChangeRenderer";
import { CommandCard } from "./CommandCard";
import { ErrorCard } from "./ErrorCard";
import { SystemMessage } from "./SystemMessage";
import { UserMessage } from "./UserMessage";

interface Props {
  entry: NormalizedLogEntry;
  expansionKey: string;
}

export function DisplayConversationEntry({ entry, expansionKey }: Props) {
  switch (entry.entry_type) {
    case "thinking":
      return (
        <ThinkingCard
          content={entry.content}
          expansionKey={expansionKey}
          defaultCollapsed={entry.collapsed}
        />
      );

    case "file_edit":
    case "file_create":
    case "file_delete":
      return <FileChangeRenderer entry={entry} expansionKey={expansionKey} />;

    case "command_run":
      return <CommandCard entry={entry} expansionKey={expansionKey} />;

    case "error":
      return <ErrorCard content={entry.content} metadata={entry.metadata} />;

    case "user_message":
      return <UserMessage content={entry.content} />;

    case "system_message":
      return <SystemMessage content={entry.content} />;

    case "loading":
      return (
        <div className="px-4 py-2">
          <div className="animate-pulse text-muted-foreground">
            Processing...
          </div>
        </div>
      );

    case "tool_call":
      return (
        <div className="px-4 py-2">
          <div className="text-sm bg-muted/30 rounded p-3">
            <strong>Tool Call:</strong> {entry.content}
          </div>
        </div>
      );

    default:
      return (
        <div className="px-4 py-2 text-muted-foreground">
          <div className="text-xs">Unknown entry type: {entry.entry_type}</div>
          <div className="text-sm mt-1">{entry.content}</div>
        </div>
      );
  }
}
