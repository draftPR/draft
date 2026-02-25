import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BackendOfflineBanner } from "../BackendOfflineBanner";
import type { BackendStatus } from "@/hooks/useBackendStatus";

function makeStatus(overrides: Partial<BackendStatus> = {}): BackendStatus {
  return {
    isOffline: false,
    lastSeen: null,
    retry: vi.fn(),
    wake: vi.fn().mockResolvedValue(undefined),
    waking: false,
    ...overrides,
  };
}

describe("BackendOfflineBanner", () => {
  it("returns null when not offline", () => {
    const { container } = render(
      <BackendOfflineBanner status={makeStatus({ isOffline: false })} />,
    );

    expect(container.innerHTML).toBe("");
  });

  it("shows banner when offline", () => {
    render(
      <BackendOfflineBanner status={makeStatus({ isOffline: true })} />,
    );

    expect(screen.getByText("Backend is unreachable.")).toBeInTheDocument();
  });

  it("shows 'Never connected' when lastSeen is null", () => {
    render(
      <BackendOfflineBanner
        status={makeStatus({ isOffline: true, lastSeen: null })}
      />,
    );

    expect(screen.getByText("Never connected")).toBeInTheDocument();
  });

  it("shows relative time when lastSeen is set", () => {
    const fiveMinutesAgo = Date.now() - 5 * 60 * 1000;

    render(
      <BackendOfflineBanner
        status={makeStatus({ isOffline: true, lastSeen: fiveMinutesAgo })}
      />,
    );

    expect(screen.getByText("Last connected 5m ago")).toBeInTheDocument();
  });

  it("shows 'Start Backend' button when not waking", () => {
    render(
      <BackendOfflineBanner
        status={makeStatus({ isOffline: true, waking: false })}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Start Backend/i }),
    ).toBeInTheDocument();
  });

  it("shows 'Starting...' when waking", () => {
    render(
      <BackendOfflineBanner
        status={makeStatus({ isOffline: true, waking: true })}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Starting\.\.\./i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("calls wake() on button click", async () => {
    const user = userEvent.setup();
    const wake = vi.fn().mockResolvedValue(undefined);

    render(
      <BackendOfflineBanner
        status={makeStatus({ isOffline: true, wake })}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Start Backend/i }));
    expect(wake).toHaveBeenCalledOnce();
  });
});
