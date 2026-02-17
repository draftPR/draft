/**
 * Badge component to display PR status with live refresh
 */

import { useState, type MouseEvent } from "react";
import { GitPullRequest, ExternalLink, RefreshCw, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { refreshPRStatus } from "@/services/api";
import { toast } from "sonner";
import type { Ticket } from "@/types/api";

interface Props {
  ticket: Ticket;
  onRefresh?: () => void;
}

export function PRStatusBadge({ ticket, onRefresh }: Props) {
  const [refreshing, setRefreshing] = useState(false);

  if (!ticket.pr_number) {
    return null;
  }

  const state = ticket.pr_state || "OPEN";

  const stateConfig = {
    OPEN: {
      color: "bg-blue-500",
      label: "Open",
      icon: GitPullRequest,
    },
    CLOSED: {
      color: "bg-gray-500",
      label: "Closed",
      icon: GitPullRequest,
    },
    MERGED: {
      color: "bg-purple-500",
      label: "Merged",
      icon: CheckCircle2,
    },
  };

  const config = stateConfig[state as keyof typeof stateConfig] || stateConfig.OPEN;
  const Icon = config.icon;

  const handleRefresh = async (e: MouseEvent) => {
    e.stopPropagation();
    setRefreshing(true);

    try {
      await refreshPRStatus(ticket.id);
      toast.success("PR status refreshed");
      onRefresh?.();
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Could not fetch PR status");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Badge className={cn("gap-1.5", config.color, "text-white")}>
        <Icon className="w-3 h-3" />
        <span>PR #{ticket.pr_number}</span>
        <span className="opacity-80">•</span>
        <span>{config.label}</span>
      </Badge>

      <a
        href={ticket.pr_url || "#"}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-500 hover:text-blue-700"
        onClick={(e) => e.stopPropagation()}
      >
        <ExternalLink className="w-4 h-4" />
      </a>

      <Button
        variant="ghost"
        size="sm"
        onClick={handleRefresh}
        disabled={refreshing}
        className="h-6 w-6 p-0"
      >
        <RefreshCw
          className={cn(
            "w-3 h-3",
            refreshing && "animate-spin"
          )}
        />
      </Button>
    </div>
  );
}
