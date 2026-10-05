import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useBoard } from "@/contexts/BoardContext";
import { queryKeys } from "@/hooks/queryKeys";
import { applyPlan, fetchGoals, planChat } from "@/services/api";
import type {
  PlanChatMessage,
  PlanGoalDraft,
  PlanTicketDraft,
  PriorityBucket,
} from "@/types/api";
import { cn } from "@/lib/utils";
import {
  ArrowUp,
  Link2,
  ListChecks,
  Loader2,
  Paperclip,
  RotateCcw,
  Sparkles,
  Target,
  Trash2,
  X,
} from "lucide-react";

const MAX_CHARS = 50_000; // backend limit per message
const BUCKETS: PriorityBucket[] = ["P0", "P1", "P2", "P3"];
const BUCKET_STYLES: Record<PriorityBucket, string> = {
  P0: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  P1: "border-orange-500/30 bg-orange-500/10 text-orange-600 dark:text-orange-400",
  P2: "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400",
  P3: "border-border bg-muted text-muted-foreground",
};
const EXAMPLES = [
  "Add rate limiting to the public API and log abusive clients",
  "Break down: move auth from sessions to OAuth with Google sign-in",
];

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

interface PlanChatDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (goalIds: string[]) => void;
}

/**
 * Chat a request or meeting notes into draft goals + tickets, refine by chat
 * or inline edits, then create everything at once. The draft survives closing
 * the dialog; "Start over" or a successful create clears it. Key the dialog
 * by board id so switching boards starts fresh.
 */
export function PlanChatDialog({
  open,
  onOpenChange,
  onSuccess,
}: PlanChatDialogProps) {
  const { currentBoard } = useBoard();
  const boardId = currentBoard?.id;
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<PlanChatMessage[]>([]);
  const [goals, setGoals] = useState<PlanGoalDraft[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState<"chat" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const { data: goalList } = useQuery({
    queryKey: queryKeys.goals.byBoard(boardId ?? ""),
    queryFn: () => fetchGoals(boardId),
    enabled: open && !!boardId,
  });
  const goalTitles = new Map(goalList?.goals.map((g) => [g.id, g.title]));

  const reset = () => {
    setMessages([]);
    setGoals([]);
    setDraft("");
    setError(null);
  };

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages, loading, error]);

  const ticketCount = goals.reduce((n, g) => n + g.tickets.length, 0);
  const newGoalCount = goals.filter((g) => !g.existing_goal_id).length;
  const summary = [
    newGoalCount && plural(newGoalCount, "new goal"),
    ticketCount && plural(ticketCount, "ticket"),
  ]
    .filter(Boolean)
    .join(" · ");
  const missingTitle = goals.some(
    (g) => !g.title.trim() || g.tickets.some((t) => !t.title.trim())
  );
  const canCreate = !!summary && !missingTitle && !loading;

  const send = async () => {
    const content = draft.trim();
    if (!content || !boardId || loading) return;
    const next: PlanChatMessage[] = [...messages, { role: "user", content }];
    setMessages(next);
    setDraft("");
    setError(null);
    setLoading("chat");
    try {
      const res = await planChat(boardId, next, goals);
      setMessages([...next, { role: "assistant", content: res.reply }]);
      setGoals(res.goals);
    } catch (err) {
      setMessages(messages);
      setDraft(content);
      setError(err instanceof Error ? err.message : "Planning failed");
    } finally {
      setLoading(null);
      composerRef.current?.focus();
    }
  };

  const create = async () => {
    if (!boardId || !canCreate) return;
    setLoading("apply");
    try {
      const res = await applyPlan(boardId, goals);
      const created = [
        res.goals_created && plural(res.goals_created, "goal"),
        res.tickets_created && plural(res.tickets_created, "ticket"),
      ]
        .filter(Boolean)
        .join(" and ");
      toast.success(`Created ${created}`, {
        description: "New tickets are in Proposed, ready for review.",
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.goals.all });
      reset();
      onOpenChange(false);
      onSuccess?.(res.goal_ids);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create plan");
    } finally {
      setLoading(null);
    }
  };

  const loadFile = async (file: File | undefined) => {
    if (!file) return;
    const text = await file.text();
    setDraft((d) =>
      `${d ? `${d}\n\n` : ""}Meeting notes (${file.name}):\n${text}`.slice(
        0,
        MAX_CHARS
      )
    );
    if (text.length > MAX_CHARS) {
      toast.warning(`${file.name} was trimmed to ${MAX_CHARS} characters`);
    }
    composerRef.current?.focus();
  };

  const editGoal = (gi: number, patch: Partial<PlanGoalDraft>) =>
    setGoals((gs) => gs.map((g, i) => (i === gi ? { ...g, ...patch } : g)));
  const editTickets = (
    gi: number,
    fn: (tickets: PlanTicketDraft[]) => PlanTicketDraft[]
  ) =>
    setGoals((gs) =>
      gs.map((g, i) => (i === gi ? { ...g, tickets: fn(g.tickets) } : g))
    );
  const renameTicket = (gi: number, ti: number, title: string) =>
    editTickets(gi, (ts) => {
      // Keep blocked_by references pointing at the renamed ticket.
      const old = ts[ti].title.toLowerCase();
      return ts.map((t, i) =>
        i === ti
          ? { ...t, title }
          : t.blocked_by?.toLowerCase() === old
            ? { ...t, blocked_by: title }
            : t
      );
    });
  const cyclePriority = (gi: number, ti: number) =>
    editTickets(gi, (ts) =>
      ts.map((t, i) =>
        i === ti
          ? {
              ...t,
              priority_bucket:
                BUCKETS[
                  (BUCKETS.indexOf(t.priority_bucket) + 1) % BUCKETS.length
                ],
            }
          : t
      )
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(88vh,780px)] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b px-6 pt-5 pb-4 pr-12">
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-violet-500" />
            Plan with AI
          </DialogTitle>
          <DialogDescription>
            Describe what you want or paste meeting notes. The AI drafts goals
            and tickets; refine them in chat or edit them directly, then create
            them in one go.
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 overflow-y-auto md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] md:overflow-hidden">
          {/* Chat */}
          <section
            aria-label="Chat"
            className="flex min-h-0 flex-col border-b md:border-r md:border-b-0"
          >
            <div
              className="max-h-[45vh] min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4 md:max-h-none"
              aria-live="polite"
            >
              {messages.length === 0 && !loading ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 py-6 text-center">
                  <span className="grid h-11 w-11 place-items-center rounded-full bg-violet-500/10 text-violet-500">
                    <Sparkles className="h-5 w-5" />
                  </span>
                  <div className="space-y-1">
                    <p className="text-sm font-semibold">
                      What should get built?
                    </p>
                    <p className="max-w-xs text-xs text-muted-foreground">
                      Type a request, paste meeting notes or a call transcript,
                      or attach a notes file. Action items that need no code are
                      skipped.
                    </p>
                  </div>
                  <div className="flex w-full max-w-sm flex-col gap-1.5 pt-1">
                    {EXAMPLES.map((ex) => (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => {
                          setDraft(ex);
                          composerRef.current?.focus();
                        }}
                        className="rounded-lg border bg-background px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                      >
                        {ex}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => fileRef.current?.click()}
                      className="flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                    >
                      <Paperclip className="h-3.5 w-3.5" />
                      Attach meeting notes (.txt, .md, .vtt)
                    </button>
                  </div>
                </div>
              ) : (
                messages.map((m, i) =>
                  m.role === "user" ? (
                    <UserBubble key={i} content={m.content} />
                  ) : (
                    <AssistantBubble key={i}>{m.content}</AssistantBubble>
                  )
                )
              )}
              {loading === "chat" && (
                <AssistantBubble>
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Reading and drafting the plan...
                  </span>
                </AssistantBubble>
              )}
              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive"
                >
                  {error}
                </p>
              )}
              <div ref={endRef} />
            </div>

            <form
              className="border-t p-3"
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
            >
              <div className="rounded-xl border bg-background transition-shadow focus-within:ring-2 focus-within:ring-ring/40">
                <Textarea
                  ref={composerRef}
                  aria-label="Message"
                  placeholder={
                    goals.length
                      ? "Refine: “split the auth ticket”, “drop goal 2”, “make exports P0”..."
                      : "Describe the work or paste meeting notes..."
                  }
                  value={draft}
                  maxLength={MAX_CHARS}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setDraft(e.target.value)
                  }
                  onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                  rows={3}
                  autoFocus
                  className="max-h-48 min-h-[72px] resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
                />
                <div className="flex items-center gap-1 px-2 pb-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 gap-1.5 text-xs text-muted-foreground"
                    onClick={() => fileRef.current?.click()}
                    disabled={!!loading}
                  >
                    <Paperclip className="h-3.5 w-3.5" />
                    Notes file
                  </Button>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".txt,.md,.markdown,.vtt,.srt,.csv,text/plain,text/markdown"
                    className="hidden"
                    onChange={(e) => {
                      void loadFile(e.target.files?.[0]);
                      e.target.value = "";
                    }}
                  />
                  <span className="ml-auto hidden whitespace-nowrap text-[11px] text-muted-foreground sm:inline">
                    Enter to send · Shift+Enter newline
                  </span>
                  <Button
                    type="submit"
                    size="icon"
                    className="ml-2 h-8 w-8 rounded-full"
                    aria-label="Send"
                    disabled={!draft.trim() || !!loading || !boardId}
                  >
                    {loading === "chat" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ArrowUp className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
            </form>
          </section>

          {/* Draft plan */}
          <section
            aria-label="Draft plan"
            className="flex min-h-0 flex-col bg-muted/30"
          >
            <div className="flex items-baseline gap-2 border-b px-4 py-3">
              <h3 className="text-sm font-semibold">Draft plan</h3>
              <span className="text-xs text-muted-foreground">
                {summary || "empty"}
              </span>
            </div>

            <fieldset
              disabled={!!loading}
              className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 disabled:opacity-60"
            >
              {goals.length === 0 ? (
                <div className="flex h-full min-h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center">
                  <ListChecks className="h-6 w-6 text-muted-foreground/60" />
                  <p className="text-sm font-medium">
                    Goals and tickets appear here
                  </p>
                  <p className="max-w-xs text-xs text-muted-foreground">
                    Nothing is created until you click Create. Tickets land in
                    Proposed so you can review them on the board.
                  </p>
                </div>
              ) : (
                goals.map((g, gi) => (
                  <article
                    key={gi}
                    className="rounded-lg border bg-card shadow-xs"
                  >
                    <header className="flex items-start gap-2 p-3">
                      <Target className="mt-1.5 h-4 w-4 shrink-0 text-primary" />
                      <div className="min-w-0 flex-1">
                        {g.existing_goal_id ? (
                          <p className="py-1 text-sm font-semibold">
                            {goalTitles.get(g.existing_goal_id) ?? g.title}
                          </p>
                        ) : (
                          <TitleField
                            label="Goal title"
                            value={g.title}
                            onChange={(title) => editGoal(gi, { title })}
                            className="font-semibold"
                          />
                        )}
                        <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                          <span
                            className={cn(
                              "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                              g.existing_goal_id
                                ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                                : "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                            )}
                          >
                            {g.existing_goal_id
                              ? "Adds to existing goal"
                              : "New goal"}
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            {plural(g.tickets.length, "ticket")}
                          </span>
                        </div>
                        {g.description && !g.existing_goal_id && (
                          <p
                            className="mt-1.5 line-clamp-2 text-xs text-muted-foreground"
                            title={g.description}
                          >
                            {g.description}
                          </p>
                        )}
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                        aria-label={`Remove goal ${g.title}`}
                        onClick={() =>
                          setGoals((gs) => gs.filter((_, i) => i !== gi))
                        }
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </header>

                    {g.tickets.length > 0 && (
                      <ol className="divide-y border-t">
                        {g.tickets.map((t, ti) => (
                          <li
                            key={ti}
                            className="group flex items-start gap-2 px-3 py-2"
                          >
                            <button
                              type="button"
                              onClick={() => cyclePriority(gi, ti)}
                              title="Click to change priority"
                              aria-label={`Priority ${t.priority_bucket}, click to change`}
                              className={cn(
                                "mt-1 shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold transition-colors",
                                BUCKET_STYLES[t.priority_bucket]
                              )}
                            >
                              {t.priority_bucket}
                            </button>
                            <div className="min-w-0 flex-1">
                              <TitleField
                                label="Ticket title"
                                value={t.title}
                                onChange={(title) =>
                                  renameTicket(gi, ti, title)
                                }
                              />
                              {t.blocked_by && (
                                <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
                                  <Link2 className="h-3 w-3 shrink-0" />
                                  <span className="truncate">
                                    after “{t.blocked_by}”
                                  </span>
                                </p>
                              )}
                              {t.description && (
                                <details className="text-xs text-muted-foreground">
                                  <summary className="cursor-pointer select-none py-0.5 hover:text-foreground">
                                    Details
                                  </summary>
                                  <p className="mt-1 whitespace-pre-wrap leading-relaxed">
                                    {t.description}
                                  </p>
                                </details>
                              )}
                            </div>
                            <button
                              type="button"
                              aria-label={`Remove ticket ${t.title}`}
                              onClick={() =>
                                editTickets(gi, (ts) =>
                                  ts.filter((_, i) => i !== ti)
                                )
                              }
                              className="mt-1 shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </li>
                        ))}
                      </ol>
                    )}
                  </article>
                ))
              )}
            </fieldset>

            <div className="flex flex-wrap items-center gap-2 border-t px-4 py-3">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={reset}
                disabled={!!loading || (!messages.length && !goals.length)}
              >
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                Start over
              </Button>
              {missingTitle && (
                <span className="text-xs text-destructive">
                  Every goal and ticket needs a title.
                </span>
              )}
              <Button
                type="button"
                size="sm"
                className="ml-auto"
                onClick={() => void create()}
                disabled={!canCreate}
              >
                {loading === "apply" && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {summary ? `Create ${summary}` : "Create"}
              </Button>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Inline title editor that wraps long titles instead of cutting them off. */
function TitleField({
  label,
  value,
  onChange,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <textarea
      aria-label={label}
      rows={1}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\n/g, " "))}
      onKeyDown={(e) => e.key === "Enter" && e.preventDefault()}
      className={cn(
        "-mx-1.5 block field-sizing-content w-[calc(100%+0.75rem)] resize-none rounded-md bg-transparent px-1.5 py-1 text-sm leading-snug outline-none hover:bg-muted focus:bg-background focus:ring-2 focus:ring-ring/40",
        !value.trim() && "ring-2 ring-destructive/50",
        className
      )}
    />
  );
}

function AssistantBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-violet-500/10 text-violet-500">
        <Sparkles className="h-3.5 w-3.5" />
      </span>
      <div className="max-w-[85%] rounded-2xl rounded-tl-md bg-muted px-3.5 py-2 text-sm whitespace-pre-wrap">
        {children}
      </div>
    </div>
  );
}

function UserBubble({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const long = content.length > 500;
  return (
    <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-tr-md bg-primary px-3.5 py-2 text-sm text-primary-foreground">
      <p
        className={cn(
          "break-words whitespace-pre-wrap",
          long && !expanded && "line-clamp-5"
        )}
      >
        {content}
      </p>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="mt-1 text-xs font-medium underline-offset-2 opacity-80 hover:underline hover:opacity-100"
        >
          {expanded
            ? "Show less"
            : `Show all (${plural(content.split("\n").length, "line")})`}
        </button>
      )}
    </div>
  );
}
