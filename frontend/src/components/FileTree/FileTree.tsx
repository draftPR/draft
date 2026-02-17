/**
 * FileTree -- recursive file tree viewer for ticket worktrees.
 *
 * Displays the directory structure of a ticket's worktree
 * with expand/collapse, file type icons, and click-to-view.
 */

import { useState, useEffect } from "react";
import { ChevronRight, ChevronDown, File, Folder, FolderOpen, Loader2 } from "lucide-react";

export interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  children?: FileNode[];
  size?: number;
}

interface FileTreeProps {
  ticketId: string;
  onFileSelect?: (path: string) => void;
}

interface FileTreeNodeProps {
  node: FileNode;
  depth: number;
  onFileSelect?: (path: string) => void;
}

function getFileIcon(name: string, isDir: boolean, isOpen: boolean) {
  if (isDir) {
    return isOpen ? (
      <FolderOpen className="h-4 w-4 text-amber-500" />
    ) : (
      <Folder className="h-4 w-4 text-amber-500" />
    );
  }

  // File type colors
  const ext = name.split(".").pop()?.toLowerCase();
  const colorMap: Record<string, string> = {
    py: "text-blue-400",
    ts: "text-blue-500",
    tsx: "text-blue-500",
    js: "text-yellow-400",
    jsx: "text-yellow-400",
    json: "text-green-400",
    md: "text-gray-400",
    yaml: "text-red-400",
    yml: "text-red-400",
    css: "text-purple-400",
    html: "text-orange-400",
    sql: "text-cyan-400",
  };

  const color = colorMap[ext || ""] || "text-muted-foreground";
  return <File className={`h-4 w-4 ${color}`} />;
}

function FileTreeNode({ node, depth, onFileSelect }: FileTreeNodeProps) {
  const [expanded, setExpanded] = useState(depth < 1);

  const handleClick = () => {
    if (node.is_dir) {
      setExpanded(!expanded);
    } else {
      onFileSelect?.(node.path);
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        className="flex items-center gap-1 w-full text-left py-0.5 px-1 rounded hover:bg-accent text-sm"
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
      >
        {node.is_dir && (
          <span className="w-4 h-4 flex items-center justify-center">
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        )}
        {!node.is_dir && <span className="w-4" />}
        {getFileIcon(node.name, node.is_dir, expanded)}
        <span className="truncate">{node.name}</span>
      </button>

      {node.is_dir && expanded && node.children && (
        <div>
          {node.children
            .sort((a, b) => {
              // Directories first, then alphabetical
              if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
              return a.name.localeCompare(b.name);
            })
            .map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                onFileSelect={onFileSelect}
              />
            ))}
        </div>
      )}
    </div>
  );
}

export function FileTree({ ticketId, onFileSelect }: FileTreeProps) {
  const [tree, setTree] = useState<FileNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticketId) return;

    const backendUrl =
      import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

    setLoading(true);
    setError(null);

    fetch(`${backendUrl}/tickets/${ticketId}/worktree/tree`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load file tree: ${res.status}`);
        return res.json();
      })
      .then((data) => setTree(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [ticketId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-4 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin mr-2" />
        Loading files...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {error}
      </div>
    );
  }

  if (!tree) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        No worktree found for this ticket.
      </div>
    );
  }

  return (
    <div className="py-1">
      {tree.children?.map((child) => (
        <FileTreeNode
          key={child.path}
          node={child}
          depth={0}
          onFileSelect={onFileSelect}
        />
      ))}
    </div>
  );
}
