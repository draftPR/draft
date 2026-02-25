import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { TicketDetailSkeleton } from "../skeletons/TicketDetailSkeleton";

describe("TicketDetailSkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<TicketDetailSkeleton />);

    expect(container.firstChild).toBeInTheDocument();
  });

  it("renders multiple skeleton sections", () => {
    const { container } = render(<TicketDetailSkeleton />);

    // The component renders the Skeleton UI component multiple times
    // Each Skeleton renders a div with animation classes
    const skeletonElements = container.querySelectorAll("[class*='animate']");
    expect(skeletonElements.length).toBeGreaterThan(0);
  });

  it("renders the events section with three event skeletons", () => {
    const { container } = render(<TicketDetailSkeleton />);

    // The events section has 3 items with border-l-2 styling
    const eventItems = container.querySelectorAll(".border-l-2");
    expect(eventItems).toHaveLength(3);
  });
});
