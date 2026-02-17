import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  compact?: boolean;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  compact = false,
  className,
}: EmptyStateProps) {
  if (compact) {
    return (
      <div className={cn("flex flex-col items-center justify-center py-6 gap-2", className)}>
        <Icon className="h-5 w-5 text-muted-foreground/50" />
        <p className="text-xs text-muted-foreground">{title}</p>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col items-center justify-center py-8 gap-3 text-center", className)}>
      <Icon className="h-10 w-10 text-muted-foreground/40" />
      <div className="space-y-1">
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        {description && (
          <p className="text-xs text-muted-foreground/70 max-w-[240px]">{description}</p>
        )}
      </div>
      {action && (
        <Button variant="outline" size="sm" onClick={action.onClick} className="mt-1">
          {action.label}
        </Button>
      )}
    </div>
  );
}
