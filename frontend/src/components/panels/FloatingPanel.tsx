import React, { useEffect, useRef, useState } from 'react';
import { Button } from '../ui/button';
import { Minimize2, X, Maximize2 } from 'lucide-react';
import { usePanelStore } from './PanelStore';

interface FloatingPanelProps {
  /** Unique ID for this panel */
  id: string;
  /** Panel title */
  title: string;
  /** Panel content */
  children: React.ReactNode;
  /** Default position */
  defaultPosition?: { x: number; y: number };
  /** Default size */
  defaultSize?: { width: number; height: number };
  /** Minimum size */
  minSize?: { width: number; height: number };
  /** Optional className for styling */
  className?: string;
}

/**
 * Floating, draggable panel component.
 *
 * Provides a draggable window with minimize, maximize, and close buttons.
 * Panels are managed by PanelStore and maintain z-index ordering.
 *
 * Note: This is a simplified implementation without react-rnd.
 * For full drag-and-resize features, consider adding react-rnd.
 *
 * @example
 * ```tsx
 * <FloatingPanel
 *   id="agent-monitor"
 *   title="Agent Monitor"
 *   defaultPosition={{ x: 100, y: 100 }}
 *   defaultSize={{ width: 400, height: 300 }}
 * >
 *   <AgentStatusList />
 * </FloatingPanel>
 * ```
 */
export function FloatingPanel({
  id,
  title,
  children,
  defaultPosition = { x: 100, y: 100 },
  defaultSize = { width: 400, height: 300 },
  minSize = { width: 200, height: 150 },
  className = '',
}: FloatingPanelProps) {
  const { panels, updatePanel, minimizePanel, closePanel, bringToFront, registerPanel } =
    usePanelStore();
  const panel = panels[id];

  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const panelRef = useRef<HTMLDivElement>(null);

  // Register panel on mount
  useEffect(() => {
    if (!panel) {
      registerPanel(id, {
        id,
        x: defaultPosition.x,
        y: defaultPosition.y,
        width: defaultSize.width,
        height: defaultSize.height,
        minimized: false,
        zIndex: 1000,
      });
    }
  }, [id, panel, registerPanel, defaultPosition, defaultSize]);

  // Handle drag start
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button')) {
      // Don't drag if clicking a button
      return;
    }

    setIsDragging(true);
    setDragOffset({
      x: e.clientX - (panel?.x || 0),
      y: e.clientY - (panel?.y || 0),
    });
    bringToFront(id);
  };

  // Handle drag
  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (panel) {
        updatePanel(id, {
          x: e.clientX - dragOffset.x,
          y: e.clientY - dragOffset.y,
        });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, dragOffset, id, panel, updatePanel]);

  // Bring to front on click
  const handleClick = () => {
    bringToFront(id);
  };

  if (!panel || panel.minimized) {
    return null;
  }

  return (
    <div
      ref={panelRef}
      onClick={handleClick}
      className={`fixed bg-background border rounded-lg shadow-2xl overflow-hidden ${className}`}
      style={{
        left: `${panel.x}px`,
        top: `${panel.y}px`,
        width: `${panel.width}px`,
        height: `${panel.height}px`,
        minWidth: `${minSize.width}px`,
        minHeight: `${minSize.height}px`,
        zIndex: panel.zIndex,
        resize: 'both',
        overflow: 'auto',
      }}
    >
      {/* Header */}
      <div
        onMouseDown={handleMouseDown}
        className="panel-header flex items-center justify-between p-3 border-b cursor-move bg-secondary/50 select-none"
      >
        <span className="font-medium text-sm truncate">{title}</span>
        <div className="flex gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              minimizePanel(id);
            }}
            className="h-6 w-6 p-0"
          >
            <Minimize2 className="h-3 w-3" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              closePanel(id);
            }}
            className="h-6 w-6 p-0 hover:bg-destructive hover:text-destructive-foreground"
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="panel-content p-4 overflow-auto" style={{ height: 'calc(100% - 49px)' }}>
        {children}
      </div>
    </div>
  );
}

/**
 * Panel minimized indicator (taskbar-like).
 *
 * Shows minimized panels and allows restoring them.
 */
export function MinimizedPanels() {
  const { panels, maximizePanel, closePanel } = usePanelStore();

  const minimizedPanels = Object.values(panels).filter((p) => p.minimized);

  if (minimizedPanels.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-4 left-4 flex gap-2 z-[2000]">
      {minimizedPanels.map((panel) => (
        <Button
          key={panel.id}
          size="sm"
          variant="secondary"
          onClick={() => maximizePanel(panel.id)}
          className="flex items-center gap-2"
        >
          <Maximize2 className="h-3 w-3" />
          Panel {panel.id}
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              closePanel(panel.id);
            }}
            className="h-4 w-4 p-0 ml-1"
          >
            <X className="h-2 w-2" />
          </Button>
        </Button>
      ))}
    </div>
  );
}
