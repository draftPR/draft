import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWalkthrough } from "../useWalkthrough";

describe("useWalkthrough", () => {
  it("starts as first run with isOpen true", async () => {
    const { result } = renderHook(() => useWalkthrough());
    // After useEffect runs
    expect(result.current.isFirstRun).toBe(true);
    expect(result.current.currentStep).toBe(0);
    expect(result.current.totalSteps).toBe(6);
  });

  it("nextStep advances the step", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.nextStep());
    expect(result.current.currentStep).toBe(1);

    act(() => result.current.nextStep());
    expect(result.current.currentStep).toBe(2);
  });

  it("nextStep does not exceed totalSteps - 1", () => {
    const { result } = renderHook(() => useWalkthrough());

    for (let i = 0; i < 10; i++) {
      act(() => result.current.nextStep());
    }
    expect(result.current.currentStep).toBe(5); // totalSteps - 1
  });

  it("prevStep goes back", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.nextStep());
    act(() => result.current.nextStep());
    act(() => result.current.prevStep());
    expect(result.current.currentStep).toBe(1);
  });

  it("prevStep does not go below 0", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.prevStep());
    expect(result.current.currentStep).toBe(0);
  });

  it("goToStep navigates to specific step", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.goToStep(3));
    expect(result.current.currentStep).toBe(3);
  });

  it("goToStep clamps to valid range", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.goToStep(100));
    expect(result.current.currentStep).toBe(5);

    act(() => result.current.goToStep(-5));
    expect(result.current.currentStep).toBe(0);
  });

  it("completeWalkthrough marks as done and closes", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.completeWalkthrough());
    expect(result.current.isFirstRun).toBe(false);
    expect(result.current.isOpen).toBe(false);
    expect(localStorage.setItem).toHaveBeenCalledWith(
      "smart-kanban-walkthrough-completed",
      "1.0",
    );
  });

  it("openWalkthrough resets to step 0 and opens", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.nextStep());
    act(() => result.current.nextStep());
    act(() => result.current.closeWalkthrough());
    act(() => result.current.openWalkthrough());

    expect(result.current.isOpen).toBe(true);
    expect(result.current.currentStep).toBe(0);
  });

  it("closeWalkthrough closes without completing", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.closeWalkthrough());
    expect(result.current.isOpen).toBe(false);
    expect(result.current.isFirstRun).toBe(true);
  });

  it("resetWalkthrough clears localStorage and reopens", () => {
    const { result } = renderHook(() => useWalkthrough());

    act(() => result.current.completeWalkthrough());
    act(() => result.current.resetWalkthrough());

    expect(result.current.isFirstRun).toBe(true);
    expect(result.current.isOpen).toBe(true);
    expect(result.current.currentStep).toBe(0);
    expect(localStorage.removeItem).toHaveBeenCalledWith(
      "smart-kanban-walkthrough-completed",
    );
  });
});
