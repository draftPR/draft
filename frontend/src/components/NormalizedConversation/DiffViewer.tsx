/**
 * Syntax-highlighted diff viewer
 */

import React from "react";
import { cn } from "@/lib/utils";

interface Props {
  diff: string;
  language?: string;
}

export function DiffViewer({ diff }: Props) {
  const lines = diff.split("\n");

  return (
    <div className="border rounded bg-background overflow-hidden">
      <div className="bg-muted px-3 py-1 text-xs font-medium border-b">
        Diff
      </div>
      <div className="overflow-x-auto max-h-96">
        {lines.map((line, i) => {
          const type = line.startsWith("+")
            ? "add"
            : line.startsWith("-")
              ? "remove"
              : line.startsWith("@@")
                ? "hunk"
                : "context";

          return (
            <div
              key={i}
              className={cn(
                "px-3 py-0.5 font-mono text-xs",
                type === "add" && "bg-green-500/10 text-green-700 dark:text-green-400",
                type === "remove" && "bg-red-500/10 text-red-700 dark:text-red-400",
                type === "hunk" && "bg-blue-500/10 text-blue-700 dark:text-blue-400 font-medium",
                type === "context" && "text-muted-foreground"
              )}
            >
              {line || "\u00A0"}
            </div>
          );
        })}
      </div>
    </div>
  );
}
