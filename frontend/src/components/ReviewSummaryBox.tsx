import { useState } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { CheckCircle, ChevronDown } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./ui/popover";
import type { ReviewDecision } from "@/types/api";

interface ReviewSummaryBoxProps {
  unresolvedCount: number;
  onSubmitReview: (decision: ReviewDecision, summary: string, autoRunFix: boolean) => Promise<void>;
  isSubmitting: boolean;
  hasExistingReview?: boolean;
}

export function ReviewSummaryBox({
  unresolvedCount,
  onSubmitReview,
  isSubmitting,
  hasExistingReview = false,
}: ReviewSummaryBoxProps) {
  const [summary, setSummary] = useState("");
  const [decision, setDecision] = useState<"approved" | "changes_requested">("approved");
  const [autoRunFix, setAutoRunFix] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  
  const handleSubmit = async () => {
    if (decision === "approved") {
      await onSubmitReview("approved", summary || "Approved", false);
    } else {
      await onSubmitReview("changes_requested", summary, autoRunFix);
    }
    setIsOpen(false);
  };
  
  if (hasExistingReview) {
    return (
      <Button variant="outline" disabled className="text-emerald-600 border-emerald-600">
        <CheckCircle className="h-4 w-4 mr-2" />
        Reviewed
      </Button>
    );
  }
  
  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button className="bg-emerald-600 hover:bg-emerald-700 text-white">
          Review changes
          <ChevronDown className="h-4 w-4 ml-2" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[400px] p-0" align="end">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold text-foreground">Finish your review</h3>
          {unresolvedCount > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              {unresolvedCount} pending comment{unresolvedCount !== 1 ? "s" : ""} will be submitted
            </p>
          )}
        </div>
        
        <div className="p-4">
          {/* Summary textarea */}
          <Textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Leave a comment"
            className="min-h-[100px] bg-background border-border text-foreground mb-4"
            disabled={isSubmitting}
          />
          
          {/* Review options */}
          <div className="space-y-3 mb-4">
            {/* Approve option */}
            <label className="flex items-start gap-3 cursor-pointer p-2 rounded hover:bg-muted/50">
              <input
                type="radio"
                name="review-decision"
                value="approved"
                checked={decision === "approved"}
                onChange={() => setDecision("approved")}
                className="mt-1 text-emerald-600 focus:ring-emerald-500"
              />
              <div>
                <span className="font-medium text-foreground">Approve</span>
                <p className="text-xs text-muted-foreground">
                  Submit feedback and approve these changes
                </p>
              </div>
            </label>
            
            {/* Request changes option */}
            <label className="flex items-start gap-3 cursor-pointer p-2 rounded hover:bg-muted/50">
              <input
                type="radio"
                name="review-decision"
                value="changes_requested"
                checked={decision === "changes_requested"}
                onChange={() => setDecision("changes_requested")}
                className="mt-1 text-orange-600 focus:ring-orange-500"
              />
              <div>
                <span className="font-medium text-foreground">Request changes</span>
                <p className="text-xs text-muted-foreground">
                  Submit feedback that must be addressed before merging
                </p>
              </div>
            </label>
          </div>
          
          {/* Auto-run checkbox - only show when requesting changes */}
          {decision === "changes_requested" && (
            <label className="flex items-center gap-2 cursor-pointer mb-4 text-sm">
              <input
                type="checkbox"
                checked={autoRunFix}
                onChange={(e) => setAutoRunFix(e.target.checked)}
                className="rounded border-border bg-background text-emerald-600 focus:ring-emerald-500"
                disabled={isSubmitting}
              />
              <span className="text-foreground">
                Auto-run agent to fix issues
              </span>
            </label>
          )}
        </div>
        
        {/* Submit button */}
        <div className="border-t border-border px-4 py-3 bg-muted/30 flex justify-end">
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            {isSubmitting ? "Submitting..." : "Submit review"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

