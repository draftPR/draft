/**
 * Collapsible card for AI thinking/reasoning blocks
 */

import { useState } from "react";
import { ChevronDown, Brain } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  content: string;
  expansionKey: string;
  defaultCollapsed?: boolean;
}

export function ThinkingCard({
  content,
  defaultCollapsed = true,
}: Props) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className="px-4 py-2">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full text-left hover:bg-accent/50 rounded p-2 transition-colors"
      >
        <Brain className="w-4 h-4 text-purple-500 flex-shrink-0" />
        <span className="text-sm font-medium text-muted-foreground">
          Thinking
        </span>
        <ChevronDown
          className={cn(
            "w-4 h-4 ml-auto transition-transform",
            !collapsed && "rotate-180"
          )}
        />
      </button>

      {!collapsed && (
        <div className="mt-2 ml-6 p-3 bg-muted/30 rounded text-sm text-muted-foreground whitespace-pre-wrap">
          {content}
        </div>
      )}
    </div>
  );
}
