import { formatDistanceToNow } from "date-fns";
import type { Revision } from "@/types/api";
import { REVISION_STATUS_COLORS, REVISION_STATUS_DISPLAY } from "@/types/api";
import { Badge } from "./ui/badge";
import { GitBranch, MessageSquare } from "lucide-react";

interface RevisionsListProps {
  revisions: Revision[];
  selectedRevisionId: string | null;
  onSelectRevision: (revisionId: string) => void;
}

export function RevisionsList({
  revisions,
  selectedRevisionId,
  onSelectRevision,
}: RevisionsListProps) {
  if (revisions.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-4">
        No revisions yet
      </div>
    );
  }
  
  return (
    <div className="space-y-2">
      {revisions.map((revision) => {
        const isSelected = revision.id === selectedRevisionId;
        const timeAgo = formatDistanceToNow(new Date(revision.created_at), {
          addSuffix: true,
        });
        
        return (
          <button
            key={revision.id}
            onClick={() => onSelectRevision(revision.id)}
            className={`w-full text-left p-3 rounded-lg border transition-colors ${
              isSelected
                ? "border-primary bg-primary/10"
                : "border-border bg-card hover:border-foreground/20"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium text-foreground">
                  Revision #{revision.number}
                </span>
              </div>
              <Badge
                className={`${REVISION_STATUS_COLORS[revision.status]} text-white text-xs`}
              >
                {REVISION_STATUS_DISPLAY[revision.status]}
              </Badge>
            </div>
            
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{timeAgo}</span>
              {revision.unresolved_comment_count > 0 && (
                <span className="flex items-center gap-1 text-orange-600">
                  <MessageSquare className="h-3 w-3" />
                  {revision.unresolved_comment_count} unresolved
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

