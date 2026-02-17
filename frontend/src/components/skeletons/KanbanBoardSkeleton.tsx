import { Skeleton } from "@/components/ui/skeleton";
import { COLUMN_ORDER, STATE_DISPLAY_NAMES } from "@/types/api";

function SkeletonCard() {
  return (
    <div className="bg-card border border-border rounded px-2 py-2 space-y-2">
      <Skeleton className="h-3.5 w-full" />
      <Skeleton className="h-3.5 w-3/4" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}

export function KanbanBoardSkeleton() {
  return (
    <div>
      {/* Controls skeleton */}
      <div className="flex items-center justify-between mb-4 px-1">
        <Skeleton className="h-8 w-36" />
        <Skeleton className="h-8 w-48" />
      </div>

      {/* Columns */}
      <div className="overflow-x-auto pb-4">
        {/* Column headers */}
        <div className="flex gap-3 mb-2 px-1">
          {COLUMN_ORDER.map((state) => (
            <div key={state} className="flex-shrink-0 w-[180px]">
              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-muted-foreground">&#9679;</span>
                <span className="font-medium text-muted-foreground/60">
                  {STATE_DISPLAY_NAMES[state]}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Column cards */}
        <div className="flex gap-3 px-1">
          {COLUMN_ORDER.map((state, colIdx) => (
            <div key={state} className="flex-shrink-0 w-[180px] space-y-2">
              {Array.from({ length: colIdx < 3 ? 3 : colIdx < 5 ? 2 : 1 }).map(
                (_, i) => (
                  <SkeletonCard key={i} />
                ),
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
