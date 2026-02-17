import { Bell, Check, Trash2, AlertCircle, CheckCircle, AlertTriangle, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useNotificationStore, type AppNotification } from "@/stores/notificationStore";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

function NotificationIcon({ type }: { type: AppNotification["type"] }) {
  switch (type) {
    case "success":
      return <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />;
    case "error":
      return <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />;
    case "warning":
      return <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0" />;
    default:
      return <Info className="h-4 w-4 text-blue-500 flex-shrink-0" />;
  }
}

export function NotificationCenter() {
  const notifications = useNotificationStore((s) => s.notifications);
  const markRead = useNotificationStore((s) => s.markRead);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const clearAll = useNotificationStore((s) => s.clearAll);
  const unreadCount = useNotificationStore((s) => s.unreadCount());

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-8 relative" title="Notifications">
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center h-4 min-w-[16px] rounded-full bg-destructive text-destructive-foreground text-[10px] font-bold px-1">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <div className="flex items-center justify-between px-3 py-2 border-b">
          <span className="text-sm font-medium">Notifications</span>
          <div className="flex items-center gap-1">
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" className="h-6 text-xs px-2" onClick={markAllRead}>
                <Check className="h-3 w-3 mr-1" />
                Mark all read
              </Button>
            )}
            {notifications.length > 0 && (
              <Button variant="ghost" size="sm" className="h-6 text-xs px-2" onClick={clearAll}>
                <Trash2 className="h-3 w-3 mr-1" />
                Clear
              </Button>
            )}
          </div>
        </div>

        <div className="max-h-[360px] overflow-y-auto">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <Bell className="h-8 w-8 mb-2 opacity-30" />
              <p className="text-xs">No notifications yet</p>
            </div>
          ) : (
            notifications.map((n) => (
              <button
                key={n.id}
                className={cn(
                  "w-full text-left px-3 py-2.5 flex items-start gap-2.5 hover:bg-muted/50 transition-colors border-b border-border/30 last:border-0",
                  !n.read && "bg-muted/30",
                )}
                onClick={() => markRead(n.id)}
              >
                <NotificationIcon type={n.type} />
                <div className="flex-1 min-w-0">
                  <p className={cn("text-xs", !n.read && "font-medium")}>{n.title}</p>
                  {n.description && (
                    <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                      {n.description}
                    </p>
                  )}
                  <p className="text-[10px] text-muted-foreground/60 mt-1">
                    {formatDistanceToNow(n.timestamp, { addSuffix: true })}
                  </p>
                </div>
                {!n.read && (
                  <span className="h-2 w-2 rounded-full bg-primary flex-shrink-0 mt-1" />
                )}
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
