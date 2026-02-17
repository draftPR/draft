/**
 * Component for rendering command executions
 */

import { useState } from "react";
import { ChevronDown, Terminal, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NormalizedLogEntry, CommandRunMetadata } from "@/types/logs";

interface Props {
  entry: NormalizedLogEntry;
  expansionKey: string;
}

export function CommandCard({ entry }: Props) {
  const [expanded, setExpanded] = useState(false);
  const metadata = entry.metadata as CommandRunMetadata;
  const success = metadata.exit_code === 0;

  return (
    <div className="px-4 py-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left hover:bg-accent/50 rounded p-2 transition-colors"
      >
        <Terminal className="w-4 h-4 text-green-500 flex-shrink-0" />
        <span className="text-sm font-medium">Ran command</span>
        <code className="text-xs bg-muted px-2 py-1 rounded flex-1 truncate">
          {metadata.command}
        </code>
        {success ? (
          <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
        ) : (
          <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
        )}
        <ChevronDown
          className={cn(
            "w-4 h-4 transition-transform flex-shrink-0",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded && (
        <div className="mt-2 ml-6">
          <div className="border rounded bg-background overflow-hidden">
            <div className="bg-muted px-3 py-1 text-xs font-medium border-b flex items-center justify-between">
              <span>Command Output</span>
              <span className={cn(
                "text-xs",
                success ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
              )}>
                Exit Code: {metadata.exit_code ?? 'unknown'}
              </span>
            </div>
            {metadata.output ? (
              <pre className="p-3 text-xs overflow-x-auto max-h-64 whitespace-pre-wrap">
                {metadata.output}
              </pre>
            ) : (
              <div className="p-3 text-xs text-muted-foreground italic">
                No output captured
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
