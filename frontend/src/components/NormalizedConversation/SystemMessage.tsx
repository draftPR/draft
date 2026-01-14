/**
 * Component for rendering system messages
 */

import React from "react";

interface Props {
  content: string;
}

export function SystemMessage({ content }: Props) {
  return (
    <div className="px-4 py-2">
      <div className="text-sm text-muted-foreground whitespace-pre-wrap">
        {content}
      </div>
    </div>
  );
}
