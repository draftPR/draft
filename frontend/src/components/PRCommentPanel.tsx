/**
 * PRCommentPanel -- View and add comments to a ticket's GitHub PR.
 */

import { useState, useCallback, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { addPRComment, listPRComments } from "@/services/api";
import type { PRComment } from "@/types/api";
import {
  MessageSquare,
  Loader2,
  Send,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

interface PRCommentPanelProps {
  ticketId: string;
  prNumber: number;
}

export function PRCommentPanel({ ticketId, prNumber }: PRCommentPanelProps) {
  const [comments, setComments] = useState<PRComment[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [newComment, setNewComment] = useState("");
  const [expanded, setExpanded] = useState(false);

  const loadComments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPRComments(ticketId);
      setComments(data);
    } catch (err) {
      toast.error("Failed to load PR comments", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    if (expanded) {
      loadComments();
    }
  }, [expanded, loadComments]);

  const handleSend = useCallback(async () => {
    if (!newComment.trim()) return;
    setSending(true);
    try {
      await addPRComment(ticketId, newComment.trim());
      toast.success("Comment added");
      setNewComment("");
      loadComments();
    } catch (err) {
      toast.error("Failed to add comment", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setSending(false);
    }
  }, [ticketId, newComment, loadComments]);

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Header toggle */}
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-2 w-full p-3 text-left hover:bg-muted/50 transition-colors"
      >
        <MessageSquare className="h-4 w-4 text-muted-foreground" />
        <span className="text-[13px] font-medium">
          PR #{prNumber} Comments
        </span>
        {comments.length > 0 && (
          <span className="text-[11px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded-full">
            {comments.length}
          </span>
        )}
      </button>

      {expanded && (
        <div className="border-t border-border p-3 space-y-3">
          {/* Comment list */}
          {loading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          ) : comments.length === 0 ? (
            <p className="text-[12px] text-muted-foreground text-center py-2">
              No comments yet
            </p>
          ) : (
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {comments.map((c, i) => (
                <div
                  key={i}
                  className="bg-muted/30 rounded-md p-2 space-y-1"
                >
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="font-medium">{c.author}</span>
                    {c.created_at && (
                      <span>
                        {new Date(c.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <p className="text-[12px] whitespace-pre-wrap">{c.body}</p>
                </div>
              ))}
            </div>
          )}

          {/* Refresh */}
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="ghost"
              onClick={loadComments}
              disabled={loading}
              className="h-7 px-2"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>

          {/* New comment input */}
          <div className="flex gap-2">
            <textarea
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              placeholder="Add a comment..."
              rows={2}
              className="flex-1 min-h-[60px] rounded-md border border-input bg-transparent px-3 py-2 text-[12px] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  handleSend();
                }
              }}
            />
            <Button
              size="sm"
              onClick={handleSend}
              disabled={sending || !newComment.trim()}
              className="self-end"
            >
              {sending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
