import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import type {
  Revision,
  RevisionDetail,
  ReviewComment,
  ReviewDecision,
  DiffFile,
} from "@/types/api";
import { REVISION_STATUS_COLORS, REVISION_STATUS_DISPLAY, RevisionStatus } from "@/types/api";
import {
  fetchRevision,
  fetchRevisionDiff,
  fetchRevisionComments,
  addReviewComment,
  resolveComment,
  unresolveComment,
  submitReview,
} from "@/services/api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { DiffViewer } from "./DiffViewer";
import { ReviewSummaryBox } from "./ReviewSummaryBox";
import { RevisionsList } from "./RevisionsList";
import {
  GitBranch,
  FileCode,
  MessageSquare,
  ChevronLeft,
  Loader2,
  RefreshCw,
} from "lucide-react";

interface RevisionViewerProps {
  ticketId: string;
  ticketTitle: string;
  revisions: Revision[];
  onRevisionUpdated: () => void;
  onClose?: () => void;
}

export function RevisionViewer({
  ticketTitle,
  revisions,
  onRevisionUpdated,
  onClose,
}: RevisionViewerProps) {
  const [selectedRevisionId, setSelectedRevisionId] = useState<string | null>(
    revisions[0]?.id || null
  );
  const [revisionDetail, setRevisionDetail] = useState<RevisionDetail | null>(null);
  const [diffFiles, setDiffFiles] = useState<DiffFile[]>([]);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  
  // Load revision details when selection changes
  const loadRevisionDetails = useCallback(async (revisionId: string) => {
    setIsLoading(true);
    try {
      const [detail, diff, commentList] = await Promise.all([
        fetchRevision(revisionId),
        fetchRevisionDiff(revisionId),
        fetchRevisionComments(revisionId),
      ]);
      
      setRevisionDetail(detail);
      setDiffFiles(diff.files);
      setComments(commentList.comments);
      
      // Select first file by default
      if (diff.files.length > 0 && !selectedFile) {
        setSelectedFile(diff.files[0].path);
      }
    } catch (error) {
      console.error("Failed to load revision details:", error);
      toast.error("Failed to load revision details");
    } finally {
      setIsLoading(false);
    }
  }, [selectedFile]);
  
  useEffect(() => {
    if (selectedRevisionId) {
      loadRevisionDetails(selectedRevisionId);
    }
  }, [selectedRevisionId, loadRevisionDetails]);
  
  // Handlers
  const handleAddComment = async (
    filePath: string,
    lineNumber: number,
    body: string,
    lineContent: string
  ) => {
    if (!selectedRevisionId) return;
    
    try {
      const comment = await addReviewComment(selectedRevisionId, {
        file_path: filePath,
        line_number: lineNumber,
        body,
        line_content: lineContent,
      });
      setComments((prev) => [...prev, comment]);
      toast.success("Comment added");
    } catch (error) {
      console.error("Failed to add comment:", error);
      toast.error("Failed to add comment");
    }
  };
  
  const handleResolveComment = async (commentId: string) => {
    try {
      const updated = await resolveComment(commentId);
      setComments((prev) =>
        prev.map((c) => (c.id === commentId ? updated : c))
      );
      toast.success("Comment resolved");
    } catch (error) {
      console.error("Failed to resolve comment:", error);
      toast.error("Failed to resolve comment");
    }
  };
  
  const handleUnresolveComment = async (commentId: string) => {
    try {
      const updated = await unresolveComment(commentId);
      setComments((prev) =>
        prev.map((c) => (c.id === commentId ? updated : c))
      );
      toast.success("Comment unresolved");
    } catch (error) {
      console.error("Failed to unresolve comment:", error);
      toast.error("Failed to unresolve comment");
    }
  };
  
  const handleSubmitReview = async (
    decision: ReviewDecision,
    summary: string,
    autoRunFix: boolean
  ) => {
    if (!selectedRevisionId) return;
    
    setIsSubmitting(true);
    try {
      await submitReview(selectedRevisionId, {
        decision,
        summary,
        auto_run_fix: autoRunFix,
      });
      
      toast.success(
        decision === "approved"
          ? "Revision approved! Ticket marked as done."
          : "Changes requested. Agent will re-run to address feedback."
      );
      
      onRevisionUpdated();
    } catch (error) {
      console.error("Failed to submit review:", error);
      toast.error("Failed to submit review");
    } finally {
      setIsSubmitting(false);
    }
  };
  
  const handleRefresh = () => {
    if (selectedRevisionId) {
      loadRevisionDetails(selectedRevisionId);
    }
    onRevisionUpdated();
  };
  
  const unresolvedCount = comments.filter((c) => !c.resolved).length;
  const hasExistingReview = revisionDetail?.status !== RevisionStatus.OPEN;
  const isReviewable = revisionDetail?.status === RevisionStatus.OPEN;
  
  return (
    <div className="flex flex-col h-full bg-background text-foreground">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {onClose && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
                className="text-muted-foreground hover:text-foreground"
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Back
              </Button>
            )}
            <div>
              <h2 className="text-lg font-semibold">{ticketTitle}</h2>
              {revisionDetail && (
                <div className="flex items-center gap-2 mt-1">
                  <GitBranch className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">
                    Revision #{revisionDetail.number}
                  </span>
                  <Badge
                    className={`${REVISION_STATUS_COLORS[revisionDetail.status]} text-white text-xs`}
                  >
                    {REVISION_STATUS_DISPLAY[revisionDetail.status]}
                  </Badge>
                </div>
              )}
            </div>
          </div>
          
          {/* Right side of header */}
          <div className="flex items-center gap-3">
            {unresolvedCount > 0 && (
              <span className="text-sm text-muted-foreground">
                {unresolvedCount} pending comment{unresolvedCount !== 1 ? "s" : ""}
              </span>
            )}
            
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={isLoading}
            >
              <RefreshCw className={`h-4 w-4 mr-1 ${isLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            
            {/* Review changes button */}
            {isReviewable ? (
              <ReviewSummaryBox
                unresolvedCount={unresolvedCount}
                onSubmitReview={handleSubmitReview}
                isSubmitting={isSubmitting}
                hasExistingReview={hasExistingReview}
              />
            ) : revisionDetail ? (
              <Badge
                className={`${REVISION_STATUS_COLORS[revisionDetail.status]} text-white`}
              >
                {REVISION_STATUS_DISPLAY[revisionDetail.status]}
              </Badge>
            ) : null}
          </div>
        </div>
      </div>
      
      {/* Main content - 2 column layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar - Revisions & Files */}
        <div className="w-[220px] flex-shrink-0 border-r border-border flex flex-col overflow-hidden">
          {/* Revisions */}
          <div className="p-3 border-b border-border">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Revisions</h3>
            <RevisionsList
              revisions={revisions}
              selectedRevisionId={selectedRevisionId}
              onSelectRevision={setSelectedRevisionId}
            />
          </div>
          
          {/* Changed Files */}
          <div className="flex-1 p-3 overflow-y-auto">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2 flex items-center gap-1">
              <FileCode className="h-3 w-3" />
              Changed Files
            </h3>
            
            {diffFiles.length === 0 ? (
              <p className="text-xs text-muted-foreground">No files changed</p>
            ) : (
              <div className="space-y-1">
                {diffFiles.map((file) => {
                  const fileComments = comments.filter(
                    (c) => c.file_path === file.path
                  );
                  const unresolvedFileComments = fileComments.filter(
                    (c) => !c.resolved
                  ).length;
                  
                  return (
                    <button
                      key={file.path}
                      onClick={() => setSelectedFile(file.path)}
                      className={`w-full text-left p-2 rounded text-xs transition-colors ${
                        selectedFile === file.path
                          ? "bg-muted text-foreground"
                          : "text-foreground hover:bg-muted/50"
                      }`}
                    >
                      <div className="truncate font-mono text-[11px]">
                        {file.path.split("/").pop()}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-[10px]">
                        <span className="text-emerald-600">+{file.additions}</span>
                        <span className="text-red-600">-{file.deletions}</span>
                        {unresolvedFileComments > 0 && (
                          <span className="text-orange-600 flex items-center gap-0.5">
                            <MessageSquare className="h-2.5 w-2.5" />
                            {unresolvedFileComments}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
        
        {/* Main content - Diff viewer (takes remaining space ~80%) */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto p-4">
              <DiffViewer
                diffPatch={revisionDetail?.diff_patch || null}
                comments={comments}
                onAddComment={handleAddComment}
                onResolveComment={handleResolveComment}
                onUnresolveComment={handleUnresolveComment}
                readOnly={!isReviewable}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

