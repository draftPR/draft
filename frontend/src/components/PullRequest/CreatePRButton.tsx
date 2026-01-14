/**
 * Button component to create a GitHub Pull Request for a ticket
 */

import React, { useState } from "react";
import { GitPullRequest, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { createPullRequest } from "@/services/api";
import type { Ticket } from "@/types/api";

interface Props {
  ticket: Ticket;
  onPRCreated?: () => void;
}

export function CreatePRButton({ ticket, onPRCreated }: Props) {
  const [creating, setCreating] = useState(false);

  // Don't show button if PR already exists
  if (ticket.pr_number) {
    return null;
  }

  // Only show button for DONE or REVIEW tickets
  if (!["DONE", "REVIEW"].includes(ticket.state)) {
    return null;
  }

  const handleCreatePR = async () => {
    setCreating(true);

    try {
      const result = await createPullRequest({
        ticket_id: ticket.id,
        title: ticket.title,
        base_branch: "main",
      });

      toast({
        title: "Pull Request Created! 🎉",
        description: (
          <div>
            <p className="mb-2">PR #{result.pr_number} created successfully</p>
            <a
              href={result.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-500 hover:underline text-sm"
            >
              View on GitHub →
            </a>
          </div>
        ),
      });

      onPRCreated?.();
    } catch (error: any) {
      toast({
        title: "Failed to Create PR",
        description: error.message || "An unexpected error occurred",
        variant: "destructive",
      });
    } finally {
      setCreating(false);
    }
  };

  return (
    <Button
      onClick={handleCreatePR}
      disabled={creating}
      size="sm"
      className="gap-2"
    >
      {creating ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin" />
          Creating PR...
        </>
      ) : (
        <>
          <GitPullRequest className="w-4 h-4" />
          Create Pull Request
        </>
      )}
    </Button>
  );
}
