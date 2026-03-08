import { useState } from 'react';
import { Card, CardContent, CardHeader } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ChevronDown, ChevronRight, File, FileCode, Plus, Minus } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import type { FileDiff } from '../../hooks/useTicketEvidence';

interface DiffViewerProps {
  diffs: FileDiff[];
  diffStat?: {
    total_files: number;
    total_additions: number;
    total_deletions: number;
  };
}

export function DiffViewer({ diffs, diffStat }: DiffViewerProps) {
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());

  const toggleFile = (filePath: string) => {
    setExpandedFiles(prev => {
      const next = new Set(prev);
      if (next.has(filePath)) {
        next.delete(filePath);
      } else {
        next.add(filePath);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedFiles(new Set(diffs.map(d => d.file_path)));
  };

  const collapseAll = () => {
    setExpandedFiles(new Set());
  };

  if (!diffs || diffs.length === 0) {
    return (
      <Card>
        <CardContent>
          <EmptyState icon={FileCode} title="No file changes" description="Diffs will appear after the agent makes code changes" />
        </CardContent>
      </Card>
    );
  }

  const renderDiffLine = (line: string, idx: number) => {
    const isAddition = line.startsWith('+') && !line.startsWith('+++');
    const isDeletion = line.startsWith('-') && !line.startsWith('---');
    const isContext = !isAddition && !isDeletion && !line.startsWith('@@');
    const isHunk = line.startsWith('@@');

    let className = 'font-mono text-xs leading-relaxed px-2';

    if (isAddition) {
      className += ' bg-green-100 dark:bg-green-950 text-green-900 dark:text-green-100';
    } else if (isDeletion) {
      className += ' bg-red-100 dark:bg-red-950 text-red-900 dark:text-red-100';
    } else if (isHunk) {
      className += ' bg-blue-100 dark:bg-blue-950 text-blue-900 dark:text-blue-100 font-semibold';
    } else if (isContext) {
      className += ' text-muted-foreground';
    }

    return (
      <div key={idx} className={className}>
        {line || ' '}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Summary */}
      {diffStat && (
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <File className="h-4 w-4" />
                  <span className="font-semibold">{diffStat.total_files} files</span>
                </div>
                <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                  <Plus className="h-4 w-4" />
                  <span>{diffStat.total_additions} additions</span>
                </div>
                <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                  <Minus className="h-4 w-4" />
                  <span>{diffStat.total_deletions} deletions</span>
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={expandAll}>
                  Expand All
                </Button>
                <Button variant="outline" size="sm" onClick={collapseAll}>
                  Collapse All
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* File diffs */}
      <div className="space-y-2">
        {diffs.map((diff, idx) => {
          const isExpanded = expandedFiles.has(diff.file_path);
          const patchLines = (diff.patch ?? '').split('\n');

          return (
            <Card key={idx}>
              <CardHeader className="py-3 cursor-pointer" onClick={() => toggleFile(diff.file_path)}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                    <File className="h-4 w-4" />
                    <span className="font-mono text-sm font-medium">{diff.file_path}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-green-600 dark:text-green-400">
                      +{diff.additions}
                    </Badge>
                    <Badge variant="secondary" className="text-red-600 dark:text-red-400">
                      -{diff.deletions}
                    </Badge>
                  </div>
                </div>
              </CardHeader>

              {isExpanded && (
                <CardContent className="pt-0">
                  <div className="rounded border bg-secondary overflow-hidden">
                    {patchLines.map((line, lineIdx) => renderDiffLine(line, lineIdx))}
                  </div>
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>

      <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            📝 <strong>These are the exact code changes made by the agent.</strong> Review each
            diff to ensure the changes match the plan and don't introduce unintended side effects.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
