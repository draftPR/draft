import { useState, useEffect } from 'react';

const WALKTHROUGH_KEY = 'smart-kanban-walkthrough-completed';
const WALKTHROUGH_VERSION = '1.0';

export interface WalkthroughState {
  isFirstRun: boolean;
  currentStep: number;
  totalSteps: number;
  isOpen: boolean;
}

export function useWalkthrough() {
  const [state, setState] = useState<WalkthroughState>({
    isFirstRun: true,
    currentStep: 0,
    totalSteps: 5,
    isOpen: false,
  });

  // Check if this is first run on mount
  useEffect(() => {
    const completed = localStorage.getItem(WALKTHROUGH_KEY);
    const isFirstRun = completed !== WALKTHROUGH_VERSION;

    setState(prev => ({
      ...prev,
      isFirstRun,
      isOpen: isFirstRun, // Auto-open on first run
    }));
  }, []);

  const nextStep = () => {
    setState(prev => ({
      ...prev,
      currentStep: Math.min(prev.currentStep + 1, prev.totalSteps - 1),
    }));
  };

  const prevStep = () => {
    setState(prev => ({
      ...prev,
      currentStep: Math.max(prev.currentStep - 1, 0),
    }));
  };

  const goToStep = (step: number) => {
    setState(prev => ({
      ...prev,
      currentStep: Math.max(0, Math.min(step, prev.totalSteps - 1)),
    }));
  };

  const completeWalkthrough = () => {
    localStorage.setItem(WALKTHROUGH_KEY, WALKTHROUGH_VERSION);
    setState(prev => ({
      ...prev,
      isFirstRun: false,
      isOpen: false,
    }));
  };

  const openWalkthrough = () => {
    setState(prev => ({
      ...prev,
      isOpen: true,
      currentStep: 0,
    }));
  };

  const closeWalkthrough = () => {
    setState(prev => ({
      ...prev,
      isOpen: false,
    }));
  };

  const resetWalkthrough = () => {
    localStorage.removeItem(WALKTHROUGH_KEY);
    setState({
      isFirstRun: true,
      currentStep: 0,
      totalSteps: 5,
      isOpen: true,
    });
  };

  return {
    ...state,
    nextStep,
    prevStep,
    goToStep,
    completeWalkthrough,
    openWalkthrough,
    closeWalkthrough,
    resetWalkthrough,
  };
}
