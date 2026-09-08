import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { suggestGoal } from "@/services/api";
import type {
  GoalSuggestAnswer,
  GoalSuggestQuestion,
  GoalSuggestion,
} from "@/types/api";
import { cn } from "@/lib/utils";
import { ArrowLeft, Check, Loader2, Sparkles } from "lucide-react";

const OTHER = "__other__";

interface GoalSuggestPanelProps {
  boardId: string;
  onApply: (suggestion: GoalSuggestion) => void;
  onCancel: () => void;
}

/**
 * Interactive "suggest a goal" flow: scan repo → choice questions → suggestion.
 * Stateless against the backend; all answers are resent each round.
 */
export function GoalSuggestPanel({
  boardId,
  onApply,
  onCancel,
}: GoalSuggestPanelProps) {
  const [task, setTask] = useState("");
  const [answers, setAnswers] = useState<GoalSuggestAnswer[]>([]);
  const [questions, setQuestions] = useState<GoalSuggestQuestion[]>([]);
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [otherText, setOtherText] = useState<Record<number, string>>({});
  const [suggestion, setSuggestion] = useState<GoalSuggestion | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stage = suggestion
    ? "suggestion"
    : questions.length
      ? "questions"
      : "task";

  const collectAnswers = (): GoalSuggestAnswer[] | null => {
    const next: GoalSuggestAnswer[] = [];
    for (let i = 0; i < questions.length; i++) {
      const choice = picked[i];
      const answer = choice === OTHER ? otherText[i]?.trim() : choice;
      if (!answer) return null;
      next.push({ question: questions[i].question, answer });
    }
    return next;
  };

  const run = async (nextAnswers: GoalSuggestAnswer[], force: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const res = await suggestGoal({
        board_id: boardId,
        task: task.trim() || null,
        answers: nextAnswers,
        force_suggest: force,
      });
      setAnswers(nextAnswers);
      setPicked({});
      setOtherText({});
      if (res.suggestion) {
        setSuggestion(res.suggestion);
        setQuestions([]);
      } else {
        setQuestions(res.questions);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suggestion failed");
    } finally {
      setLoading(false);
    }
  };

  const submitAnswers = (force: boolean) => {
    const next = collectAnswers();
    if (!next) {
      setError('Answer every question, or pick "Suggest now" to skip.');
      return;
    }
    void run([...answers, ...next], force);
  };

  const restart = () => {
    setAnswers([]);
    setQuestions([]);
    setSuggestion(null);
    setPicked({});
    setOtherText({});
    setError(null);
  };

  return (
    <div className="space-y-4" aria-busy={loading}>
      <div className="flex items-center gap-2 text-sm font-medium">
        <Sparkles className="h-4 w-4 text-violet-500" />
        Suggest a goal with AI
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {stage === "task" && "Step 1 · Describe"}
          {stage === "questions" && "Step 2 · Clarify"}
          {stage === "suggestion" && "Step 3 · Review"}
        </span>
      </div>

      {stage === "task" && (
        <div className="grid gap-2">
          <Label htmlFor="suggest-task">What do you want to achieve?</Label>
          <Textarea
            id="suggest-task"
            placeholder="e.g. Make ticket execution resilient to CLI crashes (optional — leave empty to let AI pick the most valuable goal)"
            value={task}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
              setTask(e.target.value)
            }
            disabled={loading}
            rows={3}
            autoFocus
            className="resize-none"
          />
          <p className="text-xs text-muted-foreground">
            The AI scans this board&apos;s repository, asks a few choice
            questions, then proposes a goal title and description you can edit.
          </p>
        </div>
      )}

      {stage === "questions" && (
        <div className="space-y-4 max-h-[50vh] overflow-y-auto pr-1">
          {questions.map((q, qi) => (
            <fieldset key={qi} className="space-y-1.5" disabled={loading}>
              <legend className="text-sm font-medium mb-1.5">
                {q.question}
              </legend>
              {[...q.options, OTHER].map((opt) => {
                const isOther = opt === OTHER;
                const checked = picked[qi] === opt;
                const id = `suggest-q${qi}-${isOther ? "other" : opt}`;
                return (
                  <label
                    key={opt}
                    htmlFor={id}
                    className={cn(
                      "flex items-start gap-2.5 rounded-md border px-3 py-2 text-sm cursor-pointer transition-colors",
                      checked
                        ? "border-primary bg-accent text-accent-foreground"
                        : "hover:bg-muted/50"
                    )}
                  >
                    <input
                      id={id}
                      type="radio"
                      name={`suggest-q${qi}`}
                      value={opt}
                      checked={checked}
                      onChange={() => setPicked((p) => ({ ...p, [qi]: opt }))}
                      className="mt-1 accent-primary"
                    />
                    {isOther ? (
                      <span className="flex-1 space-y-1.5">
                        <span>Other</span>
                        {checked && (
                          <Input
                            aria-label={`Your answer to: ${q.question}`}
                            placeholder="Type your own answer..."
                            value={otherText[qi] ?? ""}
                            onChange={(
                              e: React.ChangeEvent<HTMLInputElement>
                            ) =>
                              setOtherText((t) => ({
                                ...t,
                                [qi]: e.target.value,
                              }))
                            }
                            autoFocus
                            className="h-8 text-sm"
                          />
                        )}
                      </span>
                    ) : (
                      <span className="flex-1">{opt}</span>
                    )}
                  </label>
                );
              })}
            </fieldset>
          ))}
        </div>
      )}

      {stage === "suggestion" && suggestion && (
        <div className="rounded-lg border border-primary/40 bg-accent p-3 space-y-2">
          <p className="text-sm font-semibold">{suggestion.title}</p>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap max-h-48 overflow-y-auto">
            {suggestion.description}
          </p>
        </div>
      )}

      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={stage === "task" ? onCancel : restart}
          disabled={loading}
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          {stage === "task" ? "Back" : "Start over"}
        </Button>
        <span className="flex-1" />
        {stage === "task" && (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void run([], true)}
              disabled={loading}
            >
              Suggest now
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => void run([], false)}
              disabled={loading}
            >
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Scan repo &amp; ask
            </Button>
          </>
        )}
        {stage === "questions" && (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => submitAnswers(true)}
              disabled={loading}
            >
              Suggest now
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => submitAnswers(false)}
              disabled={loading}
            >
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Continue
            </Button>
          </>
        )}
        {stage === "suggestion" && suggestion && (
          <Button type="button" size="sm" onClick={() => onApply(suggestion)}>
            <Check className="mr-1 h-4 w-4" />
            Use this goal
          </Button>
        )}
      </div>
    </div>
  );
}
