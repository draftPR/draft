/**
 * RepoDiscoveryDialog - Discover repositories and create boards for them
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useBoard } from '@/contexts/BoardContext';
import {
  discoverRepos,
  createBoard,
} from '@/services/api';
import type { DiscoveredRepo } from '@/types/api';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Loader2, Search, FolderGit2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useUIStore } from '@/stores/uiStore';

interface RepoDiscoveryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReposAdded?: () => void;
}

export function RepoDiscoveryDialog({
  open,
  onOpenChange,
  onReposAdded,
}: RepoDiscoveryDialogProps) {
  const navigate = useNavigate();
  const { refreshBoards, setCurrentBoard } = useBoard();
  const [searchPath, setSearchPath] = useState('~/code');
  const [discoveredRepos, setDiscoveredRepos] = useState<DiscoveredRepo[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [discovering, setDiscovering] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handleDiscover = useCallback(async () => {
    if (!searchPath.trim()) {
      toast.error('Please enter a path to scan');
      return;
    }

    setDiscovering(true);
    setDiscoveredRepos([]);
    setSelectedPaths(new Set());
    setError(null);

    try {
      const response = await discoverRepos({
        search_paths: [searchPath],
        max_depth: 3,
      });

      const validRepos = response.discovered.filter(r => r.is_valid);
      setDiscoveredRepos(validRepos);

      if (validRepos.length === 0) {
        toast.info('No git repositories found', {
          description: `No repositories found in ${searchPath}`,
        });
      } else {
        toast.success(`Found ${validRepos.length} repository${validRepos.length > 1 ? 's' : ''}`);
      }
    } catch (error) {
      console.error('Discovery failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setError(errorMessage);
      toast.error('Failed to discover repositories', {
        description: errorMessage,
      });
    } finally {
      setDiscovering(false);
    }
  }, [searchPath]);

  async function handleAddSelected() {
    if (selectedPaths.size === 0) return;

    setAdding(true);

    try {
      let addedCount = 0;
      let errorCount = 0;
      let lastCreatedBoardId: string | null = null;

      for (const path of selectedPaths) {
        try {
          // Find the discovered repo metadata for this path
          const repoMetadata = discoveredRepos.find(r => r.path === path);

          if (!repoMetadata) {
            console.error(`Could not find metadata for ${path}`);
            errorCount++;
            continue;
          }

          // Create a new board for this repository
          const board = await createBoard({
            name: repoMetadata.display_name || repoMetadata.name,
            repo_root: path,
            default_branch: repoMetadata.default_branch || undefined,
          });

          lastCreatedBoardId = board.id;
          addedCount++;
        } catch (error) {
          console.error(`Failed to create board for repo ${path}:`, error);
          errorCount++;
        }
      }

      if (addedCount > 0) {
        toast.success(`Created ${addedCount} board${addedCount > 1 ? 's' : ''}`);
        await refreshBoards();
        onReposAdded?.();
        onOpenChange(false);

        // Auto-navigate to the newly created board and open team setup
        if (lastCreatedBoardId) {
          setCurrentBoard(lastCreatedBoardId);
          navigate(`/boards/${lastCreatedBoardId}`);
          // Open Board Settings on the Agent Team tab so the user can configure their team
          setTimeout(() => useUIStore.getState().setBoardSettingsOpen(true, "team"), 100);
        }

        if (errorCount > 0) {
          toast.warning(`${addedCount} created, ${errorCount} failed`);
        }
      } else if (errorCount > 0) {
        toast.error(`Failed to create ${errorCount} board${errorCount > 1 ? 's' : ''}`, {
          description: "Check that the repositories exist and aren't already added.",
        });
      }
    } catch (error) {
      console.error('Failed to create boards:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      toast.error('Failed to create boards', {
        description: errorMessage,
      });
    } finally {
      setAdding(false);
    }
  }

  function togglePath(path: string) {
    const newSet = new Set(selectedPaths);
    if (newSet.has(path)) {
      newSet.delete(path);
    } else {
      newSet.add(path);
    }
    setSelectedPaths(newSet);
  }

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setDiscoveredRepos([]);
      setSelectedPaths(new Set());
      setError(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Discover Repositories</DialogTitle>
          <DialogDescription>
            Scan your filesystem for git repositories and create boards for them
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
          {/* Search input */}
          <div className="flex gap-2">
            <Input
              placeholder="Path to scan (e.g., ~/code, ~/projects)"
              value={searchPath}
              onChange={(e) => setSearchPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !discovering) {
                  handleDiscover();
                }
              }}
              disabled={discovering}
            />
            <Button
              onClick={handleDiscover}
              disabled={discovering || !searchPath}
            >
              {discovering ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Scanning...
                </>
              ) : (
                <>
                  <Search className="mr-2 h-4 w-4" />
                  Scan
                </>
              )}
            </Button>
          </div>

          {/* Results */}
          {discoveredRepos.length > 0 ? (
            <>
              <div className="text-sm text-muted-foreground">
                Found {discoveredRepos.length} repositories
              </div>

              <div className="flex-1 overflow-y-auto space-y-2 border rounded-lg p-2">
                {discoveredRepos.map((repo) => (
                  <div
                    key={repo.path}
                    className="flex items-start gap-3 p-3 border rounded hover:bg-accent/50 transition-colors cursor-pointer"
                    onClick={() => togglePath(repo.path)}
                  >
                    <Checkbox
                      checked={selectedPaths.has(repo.path)}
                      onCheckedChange={() => togglePath(repo.path)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <FolderGit2 className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium">{repo.name}</span>
                        {repo.default_branch && (
                          <Badge variant="secondary" className="text-xs">
                            {repo.default_branch}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground break-all">
                        {repo.path}
                      </p>
                      {repo.remote_url && (
                        <p className="text-xs text-muted-foreground mt-1 truncate">
                          {repo.remote_url}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : discovering ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">
                  Scanning for git repositories...
                </p>
              </div>
            </div>
          ) : error ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <AlertCircle className="h-8 w-8 mx-auto mb-2 text-red-500" />
                <p className="text-sm font-medium text-red-600 mb-1">
                  Discovery failed
                </p>
                <p className="text-xs text-muted-foreground max-w-md">
                  {error}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-muted-foreground">
                <FolderGit2 className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">
                  Edit the path above if needed, then click Scan
                </p>
                <p className="text-xs mt-1 opacity-70">
                  Common paths: ~/code, ~/projects, ~/dev
                </p>
              </div>
            </div>
          )}

          {/* Actions */}
          {selectedPaths.size > 0 && (
            <div className="flex items-center justify-between pt-4 border-t">
              <span className="text-sm text-muted-foreground">
                {selectedPaths.size} selected
              </span>
              <Button
                onClick={handleAddSelected}
                disabled={adding}
              >
                {adding ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating boards...
                  </>
                ) : (
                  `Create ${selectedPaths.size} Board${selectedPaths.size > 1 ? 's' : ''}`
                )}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
