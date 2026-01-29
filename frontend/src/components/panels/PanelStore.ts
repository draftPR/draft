import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

export interface Panel {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  minimized: boolean;
  zIndex: number;
}

interface PanelContextType {
  panels: Record<string, Panel>;
  updatePanel: (id: string, updates: Partial<Panel>) => void;
  minimizePanel: (id: string) => void;
  maximizePanel: (id: string) => void;
  closePanel: (id: string) => void;
  bringToFront: (id: string) => void;
  registerPanel: (id: string, panel: Panel) => void;
}

const PanelContext = createContext<PanelContextType | undefined>(undefined);

/**
 * Context provider for managing floating panel state.
 *
 * Wrap your app in this provider to enable panel management.
 */
export function PanelProvider({ children }: { children: ReactNode }) {
  const [panels, setPanels] = useState<Record<string, Panel>>({});
  const [maxZIndex, setMaxZIndex] = useState(1000);

  const registerPanel = useCallback((id: string, panel: Panel) => {
    setPanels((prev) => ({
      ...prev,
      [id]: { ...panel, zIndex: maxZIndex + 1 },
    }));
    setMaxZIndex((prev) => prev + 1);
  }, [maxZIndex]);

  const updatePanel = useCallback((id: string, updates: Partial<Panel>) => {
    setPanels((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        ...updates,
      },
    }));
  }, []);

  const minimizePanel = useCallback((id: string) => {
    setPanels((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        minimized: true,
      },
    }));
  }, []);

  const maximizePanel = useCallback((id: string) => {
    setPanels((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        minimized: false,
      },
    }));
  }, []);

  const closePanel = useCallback((id: string) => {
    setPanels((prev) => {
      const { [id]: removed, ...remaining } = prev;
      return remaining;
    });
  }, []);

  const bringToFront = useCallback((id: string) => {
    setPanels((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        zIndex: maxZIndex + 1,
      },
    }));
    setMaxZIndex((prev) => prev + 1);
  }, [maxZIndex]);

  return (
    <PanelContext.Provider
      value={{
        panels,
        updatePanel,
        minimizePanel,
        maximizePanel,
        closePanel,
        bringToFront,
        registerPanel,
      }}
    >
      {children}
    </PanelContext.Provider>
  );
}

/**
 * Hook to access panel management functions.
 */
export function usePanelStore() {
  const context = useContext(PanelContext);
  if (context === undefined) {
    throw new Error('usePanelStore must be used within a PanelProvider');
  }
  return context;
}
