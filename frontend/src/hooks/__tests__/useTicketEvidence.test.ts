import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useTicketEvidence } from "../useTicketEvidence";

describe("useTicketEvidence", () => {
  it("fetches evidence for a ticket", async () => {
    const { result } = renderHook(() => useTicketEvidence("ticket-1"));

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // MSW handler returns { evidence: [...] }
    expect(result.current.evidence).toBeDefined();
    expect(result.current.error).toBeNull();
  });
});
