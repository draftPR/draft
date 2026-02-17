import { Skeleton } from "@/components/ui/skeleton";

export function TicketDetailSkeleton() {
  return (
    <div className="space-y-10 mt-8">
      {/* Title */}
      <div className="space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>

      {/* State & Priority */}
      <div className="grid grid-cols-2 gap-8">
        <div className="space-y-3">
          <Skeleton className="h-3 w-12" />
          <Skeleton className="h-4 w-20" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-3 w-14" />
          <Skeleton className="h-4 w-24" />
        </div>
      </div>

      {/* Evidence */}
      <div className="space-y-4">
        <Skeleton className="h-3 w-32" />
        <div className="space-y-2">
          <Skeleton className="h-12 w-full rounded-md" />
          <Skeleton className="h-12 w-full rounded-md" />
        </div>
      </div>

      {/* Events */}
      <div className="space-y-4">
        <Skeleton className="h-3 w-24" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="border-l-2 border-border/50 pl-4 py-2 space-y-2">
              <div className="flex items-center justify-between">
                <Skeleton className="h-3.5 w-24" />
                <Skeleton className="h-3 w-20" />
              </div>
              <Skeleton className="h-3 w-3/4" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
