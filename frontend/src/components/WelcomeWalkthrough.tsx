import { useWalkthrough } from "@/hooks/useWalkthrough";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Target,
  FileText,
  Play,
  CheckCircle,
  GitMerge,
  Rocket,
  ChevronRight,
  ChevronLeft,
  X,
} from "lucide-react";

interface Step {
  title: string;
  description: string;
  icon: React.ReactNode;
  details: string[];
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function WelcomeWalkthrough() {
  const {
    isOpen,
    currentStep,
    totalSteps,
    nextStep,
    prevStep,
    completeWalkthrough,
    closeWalkthrough,
  } = useWalkthrough();

  const steps: Step[] = [
    {
      title: "Welcome to Draft!",
      description: "The Autonomous Delivery System for Codebases",
      icon: <Rocket className="h-8 w-8 text-blue-500" />,
      details: [
        "Draft autonomously plans, executes, and verifies code changes",
        "You define goals in plain English, AI handles the implementation",
        "Full transparency with evidence trails for every action",
        "Let's walk through your first autonomous delivery in 5 quick steps",
      ],
    },
    {
      title: "Step 1: Add a Project",
      description: "Connect a git repository to Draft",
      icon: <Target className="h-8 w-8 text-green-500" />,
      details: [
        'Click "Add Projects" to discover local git repositories',
        "Select a repository to create your first board",
        "Each board is linked to a single codebase",
        "All work happens in isolated worktrees — your main branch stays safe",
      ],
    },
    {
      title: "Step 2: Create a Goal & Generate Tickets",
      description: "Describe what you want, AI plans the work",
      icon: <FileText className="h-8 w-8 text-purple-500" />,
      details: [
        'Click "New Goal" and describe the feature or fix in plain English',
        'Click "Generate Tickets" to let AI analyze your codebase',
        "AI creates tickets with dependencies and priorities",
        "Review the proposed tickets — accept them when you're ready",
      ],
    },
    {
      title: "Step 3: Accept & Execute",
      description: "Approve tickets and let the AI agent work",
      icon: <Play className="h-8 w-8 text-amber-500" />,
      details: [
        "Review the proposed tickets and accept the ones you want",
        "Click Execute to start the AI agent on a ticket",
        "Each ticket runs in an isolated git worktree",
        "Watch real-time logs as the agent writes code",
      ],
    },
    {
      title: "Step 4: Verify & Review",
      description: "Check the AI's work before merging",
      icon: <CheckCircle className="h-8 w-8 text-teal-500" />,
      details: [
        "Verification commands run automatically after execution",
        "View the complete diff of all code changes",
        "Add inline comments on specific lines if needed",
        "Approve the revision or request changes with feedback",
      ],
    },
    {
      title: "Step 5: Merge to Main",
      description: "Safe, automated merge with cleanup",
      icon: <GitMerge className="h-8 w-8 text-red-500" />,
      details: [
        "Once approved, merge the changes into your target branch",
        "Worktrees are cleaned up automatically after merge",
        "Your feature is now in main — ready for the next goal!",
      ],
    },
  ];

  const currentStepData = steps[currentStep];
  const isLastStep = currentStep === steps.length - 1;
  const isFirstStep = currentStep === 0;

  const handleNext = () => {
    if (isLastStep) {
      completeWalkthrough();
    } else {
      nextStep();
    }
  };

  const handleSkip = () => {
    completeWalkthrough();
  };

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={closeWalkthrough}>
      <DialogContent className="max-w-2xl" showCloseButton={false}>
        <DialogHeader>
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 mt-1">{currentStepData.icon}</div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <DialogTitle className="text-xl">
                  {currentStepData.title}
                </DialogTitle>
                <Badge variant="outline" className="ml-auto">
                  {currentStep + 1} / {totalSteps}
                </Badge>
              </div>
              <DialogDescription className="text-base">
                {currentStepData.description}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-3 py-4">
          {currentStepData.details.map((detail, index) => (
            <div key={index} className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">
                <div className="h-5 w-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-medium">
                  {index + 1}
                </div>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {detail}
              </p>
            </div>
          ))}
        </div>

        {/* Progress Indicator */}
        <div className="flex gap-1 py-2">
          {steps.map((_, index) => (
            <div
              key={index}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                index === currentStep
                  ? "bg-blue-500"
                  : index < currentStep
                    ? "bg-blue-300"
                    : "bg-gray-200"
              }`}
            />
          ))}
        </div>

        <DialogFooter className="sm:justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSkip}
            className="text-muted-foreground"
          >
            <X className="h-4 w-4 mr-1.5" />
            Skip Tutorial
          </Button>

          <div className="flex gap-2">
            {!isFirstStep && (
              <Button variant="outline" size="sm" onClick={prevStep}>
                <ChevronLeft className="h-4 w-4 mr-1.5" />
                Previous
              </Button>
            )}
            <Button onClick={handleNext}>
              {isLastStep ? (
                <>
                  Get Started
                  <Rocket className="h-4 w-4 ml-1.5" />
                </>
              ) : (
                <>
                  Next
                  <ChevronRight className="h-4 w-4 ml-1.5" />
                </>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
