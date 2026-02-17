/**
 * BoardSelector - Dropdown to switch between projects/boards
 */

import { useBoard } from '@/contexts/BoardContext';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';

export function BoardSelector() {
  const { currentBoard, boards, setCurrentBoard, isLoading } = useBoard();

  if (isLoading) {
    return <Skeleton className="h-9 w-[220px]" />;
  }

  if (boards.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        No projects yet
      </div>
    );
  }

  return (
    <Select
      value={currentBoard?.id || ''}
      onValueChange={setCurrentBoard}
    >
      <SelectTrigger className="w-[220px]">
        <SelectValue placeholder="Select project..." />
      </SelectTrigger>
      <SelectContent>
        {boards.map((board) => (
          <SelectItem key={board.id} value={board.id}>
            <div className="flex flex-col">
              <span className="font-medium">{board.name}</span>
              {board.description && (
                <span className="text-xs text-muted-foreground truncate max-w-[180px]">
                  {board.description}
                </span>
              )}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
