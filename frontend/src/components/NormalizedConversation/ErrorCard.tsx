/**
 * Component for rendering error messages
 */

import { AlertCircle } from "lucide-react";
import type { ErrorMetadata } from "@/types/logs";

interface Props {
  content: string;
  metadata: Record<string, any>;
}

export function ErrorCard({ content, metadata }: Props) {
  const errorMeta = metadata as ErrorMetadata;

  return (
    <div className="px-4 py-2">
      <div className="flex items-start gap-2 bg-destructive/10 border border-destructive/20 rounded p-3">
        <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="font-medium text-destructive mb-1">Error</div>
          {errorMeta.error_type && (
            <div className="text-sm font-mono text-destructive/90 mb-1">
              {errorMeta.error_type}
            </div>
          )}
          <div className="text-sm text-destructive/90 whitespace-pre-wrap">
            {content}
          </div>
          {errorMeta.traceback && (
            <details className="mt-2">
              <summary className="text-xs text-destructive/70 cursor-pointer hover:text-destructive">
                Show traceback
              </summary>
              <pre className="mt-1 text-xs text-destructive/70 overflow-x-auto max-h-48 p-2 bg-destructive/5 rounded">
                {errorMeta.traceback}
              </pre>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
