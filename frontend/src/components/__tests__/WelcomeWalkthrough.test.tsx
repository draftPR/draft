import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { WelcomeWalkthrough } from "@/components/WelcomeWalkthrough";

vi.mock("@/hooks/useWalkthrough", () => ({
  useWalkthrough: vi.fn(),
}));

import { useWalkthrough } from "@/hooks/useWalkthrough";

const defaultWalkthroughState = {
  isFirstRun: true,
  currentStep: 0,
  totalSteps: 6,
  isOpen: true,
  nextStep: vi.fn(),
  prevStep: vi.fn(),
  goToStep: vi.fn(),
  completeWalkthrough: vi.fn(),
  openWalkthrough: vi.fn(),
  closeWalkthrough: vi.fn(),
  resetWalkthrough: vi.fn(),
};

describe("WelcomeWalkthrough", () => {
  beforeEach(() => {
    vi.mocked(useWalkthrough).mockReturnValue(defaultWalkthroughState);
  });

  it("returns null when not open", () => {
    vi.mocked(useWalkthrough).mockReturnValue({
      ...defaultWalkthroughState,
      isOpen: false,
    });

    render(<WelcomeWalkthrough />);
    // The component returns null when not open, but the Dialog wrapper might still render
    // We check that the dialog content is not visible
    expect(screen.queryByText("Welcome to Draft!")).not.toBeInTheDocument();
  });

  it("renders the first step title when open", () => {
    render(<WelcomeWalkthrough />);
    expect(screen.getByText("Welcome to Draft!")).toBeInTheDocument();
  });

  it("renders step description", () => {
    render(<WelcomeWalkthrough />);
    expect(
      screen.getByText("The Autonomous Delivery System for Codebases"),
    ).toBeInTheDocument();
  });

  it("renders step counter badge", () => {
    render(<WelcomeWalkthrough />);
    expect(screen.getByText("1 / 6")).toBeInTheDocument();
  });

  it("renders Next button on first step", () => {
    render(<WelcomeWalkthrough />);
    expect(screen.getByText("Next")).toBeInTheDocument();
  });

  it("does not render Previous button on first step", () => {
    render(<WelcomeWalkthrough />);
    expect(screen.queryByText("Previous")).not.toBeInTheDocument();
  });

  it("renders Previous button on middle step", () => {
    vi.mocked(useWalkthrough).mockReturnValue({
      ...defaultWalkthroughState,
      currentStep: 2,
    });
    render(<WelcomeWalkthrough />);
    expect(screen.getByText("Previous")).toBeInTheDocument();
  });

  it("renders Get Started button on last step", () => {
    vi.mocked(useWalkthrough).mockReturnValue({
      ...defaultWalkthroughState,
      currentStep: 5,
    });
    render(<WelcomeWalkthrough />);
    expect(screen.getByText("Get Started")).toBeInTheDocument();
  });

  it("renders Skip Tutorial button", () => {
    render(<WelcomeWalkthrough />);
    expect(screen.getByText("Skip Tutorial")).toBeInTheDocument();
  });

  it("renders details for the first step", () => {
    render(<WelcomeWalkthrough />);
    expect(
      screen.getByText(
        /Draft autonomously plans, executes, and verifies/,
      ),
    ).toBeInTheDocument();
  });
});
