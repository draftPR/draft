/**
 * Component for rendering file changes (edit/create/delete)
 */

import { useState } from "react";
import { ChevronDown, FileEdit, FilePlus, FileX } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NormalizedLogEntry, FileEditMetadata } from "@/types/logs";
import { DiffViewer } from "./DiffViewer";

interface Props {
  entry: NormalizedLogEntry;
  expansionKey: string;
}

export function FileChangeRenderer({ entry }: Props) {
  const [expanded, setExpanded] = useState(false);
  const metadata = entry.metadata as FileEditMetadata;

  const icon =
    entry.entry_type === "file_edit"
      ? FileEdit
      : entry.entry_type === "file_create"
        ? FilePlus
        : FileX;

  const Icon = icon;

  const iconColor =
    entry.entry_type === "file_edit"
      ? "text-blue-500"
      : entry.entry_type === "file_create"
        ? "text-green-500"
        : "text-red-500";

  return (
    <div className="px-4 py-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left hover:bg-accent/50 rounded p-2 transition-colors"
      >
        <Icon className={cn("w-4 h-4 flex-shrink-0", iconColor)} />
        <span className="text-sm font-medium">{entry.content}</span>
        <span className="text-xs text-muted-foreground ml-auto mr-2 font-mono">
          {metadata.file_path}
        </span>
        <ChevronDown
          className={cn(
            "w-4 h-4 transition-transform flex-shrink-0",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded && metadata.diff && (
        <div className="mt-2 ml-6">
          <DiffViewer diff={metadata.diff} language={metadata.language} />
        </div>
      )}

      {expanded && !metadata.diff && metadata.new_content && (
        <div className="mt-2 ml-6">
          <div className="border rounded bg-background overflow-hidden">
            <div className="bg-muted px-3 py-1 text-xs font-medium border-b">
              {metadata.file_path}
            </div>
            <pre className="p-3 text-xs overflow-x-auto max-h-96">
              <code>{metadata.new_content}</code>
            </pre>
          </div>
        </div>
      )}

      {expanded && !metadata.diff && !metadata.new_content && (
        <div className="mt-2 ml-6 text-xs text-muted-foreground italic">
          No content preview available
        </div>
      )}
    </div>
  );
}
