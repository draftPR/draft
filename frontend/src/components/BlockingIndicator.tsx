import { Lock, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

interface BlockingIndicatorProps {
  blockedByTicketId: string;
  blockedByTicketTitle?: string | null;
  onNavigateToBlocker?: (ticketId: string) => void;
  compact?: boolean;
}

export function BlockingIndicator({
  blockedByTicketId,
  blockedByTicketTitle,
  onNavigateToBlocker,
  compact = false
}: BlockingIndicatorProps) {
  const displayTitle = blockedByTicketTitle || "Unknown ticket";
  const displayText = compact
    ? `🔒 ${displayTitle.slice(0, 15)}...`
    : `Blocked by: ${displayTitle}`;

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 px-2 py-1 rounded text-[10px]",
        "bg-amber-100 dark:bg-amber-900/30",
        "text-amber-700 dark:text-amber-400",
        "border border-amber-200 dark:border-amber-800",
        "transition-colors",
        onNavigateToBlocker && "cursor-pointer hover:bg-amber-200 dark:hover:bg-amber-900/50",
        compact ? "w-fit" : "w-full"
      )}
      onClick={(e) => {
        if (onNavigateToBlocker) {
          e.stopPropagation();
          onNavigateToBlocker(blockedByTicketId);
        }
      }}
      title={onNavigateToBlocker ? "Click to view blocker ticket" : undefined}
    >
      <Lock className="h-3 w-3 flex-shrink-0" />
      <span className="flex-1 truncate">{displayText}</span>
      {onNavigateToBlocker && (
        <ExternalLink className="h-3 w-3 flex-shrink-0 opacity-50" />
      )}
    </div>
  );
}
