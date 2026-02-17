/**
 * Section -- reusable content section with heading.
 */

import type { ReactNode } from "react";

interface SectionProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Section({ title, children, className = "" }: SectionProps) {
  return (
    <section className={`space-y-3 ${className}`}>
      {title && (
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      )}
      {children}
    </section>
  );
}
