import React, { useState } from "react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import type { ReviewComment } from "@/types/api";
import { CommentThread } from "./CommentThread";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

interface DiffViewerProps {
  diffPatch: string | null;
  comments: ReviewComment[];
  onAddComment: (filePath: string, lineNumber: number, body: string, lineContent: string) => Promise<void>;
  onResolveComment: (commentId: string) => Promise<void>;
  onUnresolveComment: (commentId: string) => Promise<void>;
  readOnly?: boolean;
}

interface ParsedDiff {
  filePath: string;
  oldContent: string;
  newContent: string;
  hunkHeaders: string[];
}

function parseDiffPatch(patch: string): ParsedDiff[] {
  const files: ParsedDiff[] = [];
  
  // Split by file
  const fileParts = patch.split(/^diff --git /m).filter(Boolean);
  
  for (const part of fileParts) {
    const fullPart = "diff --git " + part;
    const fileMatch = /^diff --git a\/(.+?) b\/(.+)$/m.exec(fullPart);
    if (!fileMatch) continue;
    
    const filePath = fileMatch[2];
    const oldLines: string[] = [];
    const newLines: string[] = [];
    const hunkHeaders: string[] = [];
    
    // Find hunks
    const lines = fullPart.split("\n");
    let inHunk = false;
    
    for (const line of lines) {
      if (line.startsWith("@@")) {
        inHunk = true;
        hunkHeaders.push(line);
        continue;
      }
      
      if (!inHunk) continue;
      
      if (line.startsWith("-") && !line.startsWith("---")) {
        oldLines.push(line.substring(1));
      } else if (line.startsWith("+") && !line.startsWith("+++")) {
        newLines.push(line.substring(1));
      } else if (line.startsWith(" ")) {
        oldLines.push(line.substring(1));
        newLines.push(line.substring(1));
      }
    }
    
    files.push({
      filePath,
      oldContent: oldLines.join("\n"),
      newContent: newLines.join("\n"),
      hunkHeaders,
    });
  }
  
  return files;
}

interface AddCommentBoxProps {
  onSubmit: (body: string) => void;
  onCancel: () => void;
  isSubmitting: boolean;
  lineNumber: number;
}

function AddCommentBox({ onSubmit, onCancel, isSubmitting, lineNumber }: AddCommentBoxProps) {
  const [body, setBody] = useState("");
  
  const handleSubmit = () => {
    if (body.trim()) {
      onSubmit(body.trim());
      setBody("");
    }
  };

  // Handle keyboard shortcuts
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onCancel();
    } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleSubmit();
    }
  };
  
  return (
    <div className="bg-white border border-slate-300 rounded-md shadow-lg overflow-hidden">
      {/* Header */}
      <div className="bg-slate-50 px-3 py-2 border-b border-slate-200 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">
          Comment on line {lineNumber}
        </span>
        <span className="text-xs text-slate-500">
          Ctrl+Enter to submit
        </span>
      </div>
      
      {/* Textarea */}
      <div className="p-3">
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Leave a comment..."
          className="min-h-[100px] bg-white border-slate-300 text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-blue-500"
          disabled={isSubmitting}
          autoFocus
        />
      </div>
      
      {/* Footer with buttons */}
      <div className="bg-slate-50 px-3 py-2 border-t border-slate-200 flex justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
          className="text-slate-600 border-slate-300 hover:bg-slate-100"
        >
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={!body.trim() || isSubmitting}
          className="bg-emerald-600 hover:bg-emerald-700 text-white"
        >
          {isSubmitting ? "Adding..." : "Add comment"}
        </Button>
      </div>
    </div>
  );
}

interface FileDiffProps {
  file: ParsedDiff;
  comments: ReviewComment[];
  onAddComment: (lineNumber: number, body: string, lineContent: string) => Promise<void>;
  onResolveComment: (commentId: string) => Promise<void>;
  onUnresolveComment: (commentId: string) => Promise<void>;
  readOnly?: boolean;
}

function FileDiff({
  file,
  comments,
  onAddComment,
  onResolveComment,
  onUnresolveComment,
  readOnly
}: FileDiffProps) {
  const [addingCommentLine, setAddingCommentLine] = useState<number | null>(null);
  const [commentBoxTop, setCommentBoxTop] = useState<number>(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [commentPositions, setCommentPositions] = useState<Record<number, number>>({});
  const diffContainerRef = { current: null as HTMLDivElement | null };
  // Track if the library's click handler was called (for fallback detection)
  const libraryHandlerCalledRef = { current: false };

  // Group comments by line number
  const commentsByLine = comments.reduce((acc, comment) => {
    if (!acc[comment.line_number]) {
      acc[comment.line_number] = [];
    }
    acc[comment.line_number].push(comment);
    return acc;
  }, {} as Record<number, ReviewComment[]>);

  // Calculate positions for all comment threads when comments change
  React.useEffect(() => {
    if (!diffContainerRef.current || Object.keys(commentsByLine).length === 0) {
      return;
    }

    const newPositions: Record<number, number> = {};
    const container = diffContainerRef.current;
    const rows = container.querySelectorAll('tr');

    for (const [lineNumStr] of Object.entries(commentsByLine)) {
      const lineNum = parseInt(lineNumStr, 10);

      for (const row of rows) {
        const lineNumberCells = row.querySelectorAll('pre');
        for (const pre of lineNumberCells) {
          if (pre.textContent?.trim() === String(lineNum)) {
            const rowRect = row.getBoundingClientRect();
            const containerRect = container.getBoundingClientRect();
            newPositions[lineNum] = rowRect.bottom - containerRect.top;
            break;
          }
        }
        if (newPositions[lineNum]) break;
      }
    }

    setCommentPositions(newPositions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commentsByLine, file]);
  
  const handleAddComment = async (body: string) => {
    if (addingCommentLine === null) return;
    
    setIsSubmitting(true);
    try {
      // Get the line content for anchor computation
      const lines = file.newContent.split("\n");
      const lineContent = lines[addingCommentLine - 1] || "";
      await onAddComment(addingCommentLine, body, lineContent);
      setAddingCommentLine(null);
    } finally {
      setIsSubmitting(false);
    }
  };
  
  // Calculate the position for the comment box based on the clicked line
  const calculateCommentPosition = (lineNum: number, clickEvent?: React.MouseEvent) => {
    if (!diffContainerRef.current) return 0;
    
    // Try to find the row containing this line number
    const container = diffContainerRef.current;
    const rows = container.querySelectorAll('tr');
    
    for (const row of rows) {
      const lineNumberCells = row.querySelectorAll('pre');
      for (const pre of lineNumberCells) {
        if (pre.textContent?.trim() === String(lineNum)) {
          // Found the row - get its position relative to container
          const rowRect = row.getBoundingClientRect();
          const containerRect = container.getBoundingClientRect();
          return rowRect.bottom - containerRect.top;
        }
      }
    }
    
    // Fallback: use click event position
    if (clickEvent) {
      const containerRect = container.getBoundingClientRect();
      return clickEvent.clientY - containerRect.top + 20;
    }
    
    return 0;
  };

  // Handle clicking on a line number to add a comment
  const handleLineNumberClick = (lineId: string, event?: React.MouseEvent) => {
    libraryHandlerCalledRef.current = true; // Mark that library handler was called
    
    if (readOnly) return;
    
    // lineId format is "${prefix}-${lineNumber}" where prefix is "L" (left/old) or "R" (right/new)
    // However, in some versions/modes, the prefix may come through as "undefined"
    const rightMatch = lineId.match(/^R-(\d+)$/);
    const leftMatch = lineId.match(/^L-(\d+)$/);
    const undefinedMatch = lineId.match(/^undefined-(\d+)$/);
    const anyMatch = lineId.match(/^.*?-(\d+)$/);
    
    let lineNum: number | null = null;
    
    if (rightMatch) {
      lineNum = parseInt(rightMatch[1], 10);
    } else if (leftMatch) {
      lineNum = parseInt(leftMatch[1], 10);
    } else if (undefinedMatch) {
      lineNum = parseInt(undefinedMatch[1], 10);
    } else if (anyMatch) {
      lineNum = parseInt(anyMatch[1], 10);
    } else {
      return;
    }
    
    // Toggle behavior: if clicking the same line, close the comment box
    if (addingCommentLine === lineNum) {
      setAddingCommentLine(null);
    } else {
      const top = calculateCommentPosition(lineNum, event);
      setCommentBoxTop(top);
      setAddingCommentLine(lineNum);
    }
  };
  
  // Custom styles for the diff viewer
  const diffStyles = {
    variables: {
      dark: {
        diffViewerBackground: "hsl(0 0% 98%)",
        diffViewerColor: "hsl(0 0% 10%)",
        addedBackground: "#06b6d420",
        addedColor: "#059669",
        removedBackground: "#dc262620",
        removedColor: "#dc2626",
        wordAddedBackground: "#05966940",
        wordRemovedBackground: "#dc262640",
        addedGutterBackground: "#06b6d430",
        removedGutterBackground: "#dc262630",
        gutterBackground: "hsl(0 0% 96%)",
        gutterBackgroundDark: "hsl(0 0% 94%)",
        highlightBackground: "hsl(0 0% 90%)",
        highlightGutterBackground: "hsl(0 0% 90%)",
        codeFoldGutterBackground: "hsl(0 0% 94%)",
        codeFoldBackground: "hsl(0 0% 96%)",
        emptyLineBackground: "hsl(0 0% 98%)",
        gutterColor: "hsl(0 0% 45%)",
        addedGutterColor: "#059669",
        removedGutterColor: "#dc2626",
        codeFoldContentColor: "hsl(0 0% 45%)",
      },
    },
    line: {
      padding: "4px 10px",
      "&:hover": {
        background: "hsl(0 0% 90%)",
      },
    },
    gutter: {
      padding: "0 10px",
      minWidth: "40px",
      cursor: readOnly ? "default" : "pointer",
      userSelect: "none",
      "&:hover": readOnly ? {} : {
        background: "hsl(0 0% 85%)",
      },
    },
    contentText: {
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      fontSize: "13px",
    },
  };
  
  return (
    <div className="border border-border rounded-lg overflow-hidden mb-4">
      <div className="bg-muted px-4 py-2 border-b border-border">
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm text-foreground">{file.filePath}</span>
          {!readOnly && (
            <span className="text-xs text-muted-foreground italic">
              Click on line numbers to add comments
            </span>
          )}
        </div>
      </div>
      
      <div 
        className="relative"
        ref={(el) => { diffContainerRef.current = el; }}
        onClick={(e) => {
          // FALLBACK: If library's onLineNumberClick doesn't work, handle clicks directly
          if (readOnly) return;
          
          const target = e.target as HTMLElement;
          const gutterCell = target.closest('td');
          if (!gutterCell) return;
          
          const cellStyle = window.getComputedStyle(gutterCell);
          const isGutter = cellStyle.cursor === 'pointer' || gutterCell.querySelector('pre');
          
          if (isGutter) {
            const preElement = gutterCell.querySelector('pre');
            const lineNumberText = preElement?.textContent?.trim();
            
            if (lineNumberText && /^\d+$/.test(lineNumberText)) {
              const lineNum = parseInt(lineNumberText, 10);
              
              if (!libraryHandlerCalledRef.current) {
                // Fallback: library handler didn't fire
                if (addingCommentLine === lineNum) {
                  setAddingCommentLine(null);
                } else {
                  const top = calculateCommentPosition(lineNum, e);
                  setCommentBoxTop(top);
                  setAddingCommentLine(lineNum);
                }
              }
              libraryHandlerCalledRef.current = false;
            }
          }
        }}
      >
        <ReactDiffViewer
          oldValue={file.oldContent}
          newValue={file.newContent}
          splitView={false}
          useDarkTheme={false}
          styles={diffStyles}
          compareMethod={DiffMethod.WORDS}
          hideLineNumbers={false}
          onLineNumberClick={handleLineNumberClick}
          showDiffOnly={false}
        />

        {/* Existing comments displayed inline next to their lines */}
        {Object.entries(commentsByLine).map(([lineNum, lineComments]) => {
          const lineNumber = parseInt(lineNum, 10);
          const top = commentPositions[lineNumber];

          // Only render if we have a calculated position
          if (top === undefined) return null;

          return (
            <div
              key={lineNum}
              className="absolute left-0 right-0 z-40 px-2"
              style={{ top: `${top}px` }}
            >
              <div className="space-y-2">
                {lineComments.map((comment) => (
                  <CommentThread
                    key={comment.id}
                    comment={comment}
                    onResolve={() => onResolveComment(comment.id)}
                    onUnresolve={() => onUnresolveComment(comment.id)}
                    readOnly={readOnly}
                  />
                ))}
              </div>
            </div>
          );
        })}

        {/* Inline comment box - positioned absolutely below the clicked line */}
        {addingCommentLine !== null && (
          <div
            className="absolute left-0 right-0 z-50 px-2"
            style={{ top: `${commentBoxTop}px` }}
            ref={(el) => el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })}
          >
            <AddCommentBox
              onSubmit={handleAddComment}
              onCancel={() => setAddingCommentLine(null)}
              isSubmitting={isSubmitting}
              lineNumber={addingCommentLine}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function DiffViewer({
  diffPatch,
  comments,
  onAddComment,
  onResolveComment,
  onUnresolveComment,
  readOnly = false,
}: DiffViewerProps) {
  if (!diffPatch) {
    return (
      <div className="text-center text-muted-foreground py-8">
        No diff content available
      </div>
    );
  }
  
  const files = parseDiffPatch(diffPatch);
  
  if (files.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8">
        No changes in this revision
      </div>
    );
  }
  
  return (
    <div className="space-y-4">
      {files.map((file) => {
        const fileComments = comments.filter((c) => c.file_path === file.filePath);
        
        return (
          <FileDiff
            key={file.filePath}
            file={file}
            comments={fileComments}
            onAddComment={(lineNumber, body, lineContent) =>
              onAddComment(file.filePath, lineNumber, body, lineContent)
            }
            onResolveComment={onResolveComment}
            onUnresolveComment={onUnresolveComment}
            readOnly={readOnly}
          />
        );
      })}
    </div>
  );
}

