/**
 * Component for rendering user messages
 */

import React from "react";
import { User } from "lucide-react";

interface Props {
  content: string;
}

export function UserMessage({ content }: Props) {
  return (
    <div className="px-4 py-2">
      <div className="flex items-start gap-2 bg-primary/10 border border-primary/20 rounded p-3">
        <User className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="font-medium text-primary mb-1">User</div>
          <div className="text-sm whitespace-pre-wrap">{content}</div>
        </div>
      </div>
    </div>
  );
}
