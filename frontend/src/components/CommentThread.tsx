import { formatDistanceToNow } from "date-fns";
import type { ReviewComment, AuthorType } from "@/types/api";
import { Button } from "./ui/button";
import { CheckCircle, Circle, User, Bot, Cpu } from "lucide-react";

interface CommentThreadProps {
  comment: ReviewComment;
  onResolve: () => Promise<void>;
  onUnresolve: () => Promise<void>;
  readOnly?: boolean;
}

const AUTHOR_ICONS: Record<AuthorType, React.ComponentType<{ className?: string }>> = {
  human: User,
  agent: Bot,
  system: Cpu,
};

const AUTHOR_LABELS: Record<AuthorType, string> = {
  human: "Reviewer",
  agent: "Agent",
  system: "System",
};

export function CommentThread({
  comment,
  onResolve,
  onUnresolve,
  readOnly = false,
}: CommentThreadProps) {
  const AuthorIcon = AUTHOR_ICONS[comment.author_type] || User;
  const authorLabel = AUTHOR_LABELS[comment.author_type] || "Unknown";
  
  const timeAgo = formatDistanceToNow(new Date(comment.created_at), {
    addSuffix: true,
  });
  
  return (
    <div
      className={`border rounded-lg p-3 mb-2 ${
        comment.resolved
          ? "border-border bg-muted/50 opacity-60"
          : "border-border bg-card"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <AuthorIcon className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-foreground">{authorLabel}</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">{timeAgo}</span>
          {comment.resolved && (
            <>
              <span className="text-muted-foreground">·</span>
              <span className="text-emerald-600 text-xs flex items-center gap-1">
                <CheckCircle className="h-3 w-3" />
                Resolved
              </span>
            </>
          )}
        </div>
        
        {!readOnly && (
          <div className="flex-shrink-0">
            {comment.resolved ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={onUnresolve}
                className="text-xs h-7 px-2 text-muted-foreground hover:text-foreground"
              >
                <Circle className="h-3 w-3 mr-1" />
                Unresolve
              </Button>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={onResolve}
                className="text-xs h-7 px-2 text-emerald-600 hover:text-emerald-700"
              >
                <CheckCircle className="h-3 w-3 mr-1" />
                Resolve
              </Button>
            )}
          </div>
        )}
      </div>
      
      {/* Show the line of code being commented on */}
      {comment.line_content && (
        <div className="mt-2 px-2 py-1.5 bg-muted rounded border border-border">
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
            <span className="font-mono">{comment.file_path}:{comment.line_number}</span>
          </div>
          <code className="text-xs font-mono text-foreground block">
            {comment.line_content}
          </code>
        </div>
      )}
      
      <div className="mt-2 text-sm text-foreground whitespace-pre-wrap">
        {comment.body}
      </div>
    </div>
  );
}

