import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Keyboard } from "lucide-react";
import { formatShortcut } from "@/hooks/useKeyboardShortcuts";
import type { KeyboardShortcut } from "@/hooks/useKeyboardShortcuts";

interface ShortcutCategory {
  name: string;
  shortcuts: KeyboardShortcut[];
}

const SHORTCUT_CATEGORIES: ShortcutCategory[] = [
  {
    name: "Navigation",
    shortcuts: [
      { key: "g", description: "Go to board", action: () => {} },
      { key: "j", description: "Move down", action: () => {} },
      { key: "k", description: "Move up", action: () => {} },
      { key: "Enter", description: "Select / Open", action: () => {} },
      { key: "Escape", description: "Close / Cancel", action: () => {} },
    ],
  },
  {
    name: "Actions",
    shortcuts: [
      { key: "n", description: "New ticket", action: () => {} },
      { key: "e", description: "Execute selected ticket", action: () => {} },
      { key: "a", description: "Accept selected tickets", action: () => {} },
      { key: "r", description: "Refresh board", action: () => {} },
      { key: "m", description: "Merge ticket", action: () => {} },
    ],
  },
  {
    name: "Search & Commands",
    shortcuts: [
      { key: "/", description: "Focus search", action: () => {} },
      { key: "k", ctrl: true, description: "Command palette", action: () => {} },
      { key: "p", ctrl: true, description: "Quick file open", action: () => {} },
    ],
  },
  {
    name: "Views",
    shortcuts: [
      { key: "b", description: "Toggle sidebar", action: () => {} },
      { key: "l", description: "Toggle logs panel", action: () => {} },
      { key: "?", description: "Show this help", action: () => {} },
    ],
  },
  {
    name: "Review",
    shortcuts: [
      { key: "c", description: "Add comment", action: () => {} },
      { key: "ArrowUp", ctrl: true, description: "Previous file", action: () => {} },
      { key: "ArrowDown", ctrl: true, description: "Next file", action: () => {} },
      { key: "Enter", shift: true, description: "Submit review", action: () => {} },
    ],
  },
];

function ShortcutBadge({ shortcut }: { shortcut: KeyboardShortcut }) {
  const formatted = formatShortcut(shortcut);
  return (
    <Badge variant="outline" className="font-mono text-xs px-2 py-0.5">
      {formatted}
    </Badge>
  );
}

interface KeyboardShortcutsHelpProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardShortcutsHelp({ open, onOpenChange }: KeyboardShortcutsHelpProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Keyboard className="h-5 w-5" />
            Keyboard Shortcuts
          </DialogTitle>
          <DialogDescription>
            Use these shortcuts to navigate and interact with Smart Kanban faster.
          </DialogDescription>
        </DialogHeader>
        
        <div className="grid gap-6 mt-4">
          {SHORTCUT_CATEGORIES.map((category) => (
            <div key={category.name}>
              <h3 className="font-semibold text-sm mb-2 text-muted-foreground uppercase tracking-wide">
                {category.name}
              </h3>
              <div className="space-y-2">
                {category.shortcuts.map((shortcut, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-1.5 border-b border-muted last:border-0"
                  >
                    <span className="text-sm">{shortcut.description}</span>
                    <ShortcutBadge shortcut={shortcut} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        
        <div className="mt-4 pt-4 border-t text-xs text-muted-foreground">
          <p>
            Tip: Press <Badge variant="outline" className="font-mono text-xs mx-1">?</Badge> 
            anytime to show this help.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
