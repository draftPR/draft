/**
 * RepoManager - Manage repositories for a board
 */

import { useState, useEffect } from 'react';
import { useBoard } from '@/contexts/BoardContext';
import {
  fetchBoardRepos,
  removeRepoFromBoard,
  updateBoardRepo,
} from '@/services/api';
import type { BoardRepo } from '@/types/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Trash2, Star, FolderGit2 } from 'lucide-react';
import { RepoDiscoveryDialog } from './RepoDiscoveryDialog';

export function RepoManager() {
  const { currentBoard, refreshBoards } = useBoard();
  const [repos, setRepos] = useState<BoardRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [discoveryDialogOpen, setDiscoveryDialogOpen] = useState(false);

  useEffect(() => {
    if (!currentBoard) {
      setLoading(false);
      return;
    }

    loadRepos();
  }, [currentBoard?.id]);

  async function loadRepos() {
    if (!currentBoard) return;

    setLoading(true);
    try {
      const response = await fetchBoardRepos(currentBoard.id);
      setRepos(response.repos);
    } catch (error) {
      console.error('Failed to load repos:', error);
    } finally {
      setLoading(false);
    }
  }

  async function handleRemoveRepo(repoId: string) {
    if (!currentBoard) return;

    if (!confirm('Remove this repository from the project?')) {
      return;
    }

    try {
      await removeRepoFromBoard(currentBoard.id, repoId);
      await loadRepos();
      await refreshBoards();
    } catch (error) {
      console.error('Failed to remove repo:', error);
      alert('Failed to remove repository');
    }
  }

  async function handleSetPrimary(repoId: string) {
    if (!currentBoard) return;

    try {
      await updateBoardRepo(currentBoard.id, repoId, { is_primary: true });
      await loadRepos();
      await refreshBoards();
    } catch (error) {
      console.error('Failed to set primary repo:', error);
      alert('Failed to set primary repository');
    }
  }

  if (!currentBoard) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Repositories</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Please select a project to manage repositories
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
          <CardTitle className="flex items-center gap-2">
            <FolderGit2 className="h-5 w-5" />
            Repositories
          </CardTitle>
          <Button
            onClick={() => setDiscoveryDialogOpen(true)}
            size="sm"
            className="flex-shrink-0"
          >
            Add Repository
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : repos.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground mb-4">
                No repositories added yet
              </p>
              <Button
                onClick={() => setDiscoveryDialogOpen(true)}
                variant="outline"
              >
                Add Your First Repository
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {repos.map((boardRepo) => (
                <div
                  key={boardRepo.id}
                  className="flex items-center justify-between p-3 border rounded-lg hover:bg-accent/50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium truncate">
                        {boardRepo.repo.display_name}
                      </span>
                      {boardRepo.is_primary && (
                        <Badge variant="default" className="flex items-center gap-1">
                          <Star className="h-3 w-3" />
                          Primary
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">
                      {boardRepo.repo.path}
                    </p>
                    {boardRepo.repo.default_branch && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Branch: {boardRepo.repo.default_branch}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    {!boardRepo.is_primary && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleSetPrimary(boardRepo.repo_id)}
                        title="Set as primary repository"
                      >
                        <Star className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveRepo(boardRepo.repo_id)}
                      className="text-destructive hover:text-destructive"
                      title="Remove repository"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <RepoDiscoveryDialog
        open={discoveryDialogOpen}
        onOpenChange={setDiscoveryDialogOpen}
        onReposAdded={loadRepos}
      />
    </>
  );
}
