import { WifiOff, Power, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { BackendStatus } from "@/hooks/useBackendStatus";

interface Props {
  status: BackendStatus;
}

export function BackendOfflineBanner({ status }: Props) {
  if (!status.isOffline) return null;

  const lastSeenText = status.lastSeen
    ? `Last connected ${formatAgo(status.lastSeen)}`
    : "Never connected";

  return (
    <div className="fixed inset-x-0 top-0 z-[100] flex items-center justify-center gap-3 bg-destructive/95 px-4 py-3 text-destructive-foreground shadow-lg backdrop-blur-sm">
      <WifiOff className="h-5 w-5 shrink-0" />
      <div className="text-sm font-medium">
        Backend is unreachable.
        <span className="ml-2 text-xs opacity-75">{lastSeenText}</span>
      </div>
      <Button
        size="sm"
        variant="secondary"
        onClick={() => status.wake()}
        disabled={status.waking}
        className="ml-2 h-7 gap-1.5"
      >
        {status.waking ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Power className="h-3.5 w-3.5" />
        )}
        {status.waking ? "Starting..." : "Start Backend"}
      </Button>
    </div>
  );
}

function formatAgo(ts: number): string {
  const secs = Math.round((Date.now() - ts) / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return `${hrs}h ago`;
}
