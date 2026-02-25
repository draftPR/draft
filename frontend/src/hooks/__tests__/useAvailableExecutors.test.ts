import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAvailableExecutors } from "../useAvailableExecutors";

describe("useAvailableExecutors", () => {
  it("fetches and returns executor list", async () => {
    const { result } = renderHook(() => useAvailableExecutors());

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.executors).toHaveLength(2);
    expect(result.current.executors[0].name).toBe("claude");
    expect(result.current.error).toBeNull();
  });
});
