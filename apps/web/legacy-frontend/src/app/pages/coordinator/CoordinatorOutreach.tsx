import { useState, useEffect } from "react";
import { Mail, Plus, Send, AlertTriangle, CheckCircle2, Sparkles } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { Dialog, DialogContent } from "../../components/ui/dialog";
import { fetchCoordinatorThreads, type OutreachThread } from "../../../lib/api";
import { AgenticOutreachPanel } from "../../../components/AgenticOutreachPanel";

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

const STATUS_COLORS: Record<OutreachThread["status"], string> = {
  confirmed: "bg-primary/10 text-primary",
  in_progress: "bg-primary/10 text-primary",
  awaiting_response: "bg-muted text-muted-foreground",
  new: "bg-muted text-muted-foreground",
};

const STATUS_LABELS: Record<OutreachThread["status"], string> = {
  confirmed: "Confirmed",
  in_progress: "In Progress",
  awaiting_response: "Awaiting Response",
  new: "New",
};

export function CoordinatorOutreach() {
  const session = getSession();
  const coordinatorId = String((session.user as Record<string, unknown> | undefined)?.coordinator_id ?? "coord-001");

  const [threads, setThreads] = useState<OutreachThread[]>([]);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sendDialog, setSendDialog] = useState<{ open: boolean; threadId: string | null }>({ open: false, threadId: null });
  const [messageText, setMessageText] = useState("");
  const [sendSuccess, setSendSuccess] = useState<string | null>(null);

  const [newThreadDialog, setNewThreadDialog] = useState(false);
  const [newEventName, setNewEventName] = useState("");
  const [newThreadSuccess, setNewThreadSuccess] = useState(false);

  const [agenticOpen, setAgenticOpen] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchCoordinatorThreads(coordinatorId);
        setThreads(result.data);
        setSource(result.source);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load threads");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [coordinatorId]);

  function handleSend() {
    console.log("Message sent:", messageText);
    setSendSuccess("Message sent!");
    setMessageText("");
    setTimeout(() => {
      setSendSuccess(null);
      setSendDialog({ open: false, threadId: null });
    }, 2000);
  }

  function handleNewThread() {
    console.log("New thread submitted for:", newEventName);
    setNewThreadSuccess(true);
    setTimeout(() => {
      setNewThreadSuccess(false);
      setNewThreadDialog(false);
      setNewEventName("");
    }, 2000);
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 rounded-xl" />
        <Skeleton className="h-28 w-full rounded-2xl" />
        <Skeleton className="h-28 w-full rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8 text-center">
        <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" />
        <p className="font-medium text-destructive">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold text-foreground">IA West Contact</h1>
          {source === "demo" && <DemoModeBadge />}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAgenticOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
          >
            <Sparkles className="h-4 w-4" />
            Launch AI Outreach Agents
          </button>
          <button
            onClick={() => setNewThreadDialog(true)}
            className="flex items-center gap-2 rounded-xl border border-border/70 px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent"
          >
            <Plus className="h-4 w-4" />
            New Thread
          </button>
        </div>
      </div>

      {/* Agentic Outreach Dialog */}
      <Dialog open={agenticOpen} onOpenChange={(open) => !open && setAgenticOpen(false)}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto rounded-2xl p-6">
          <AgenticOutreachPanel
            speakerName="Dr. Sarah Chen"
            eventName="AI for a Better Future Hackathon"
            coordinatorId={coordinatorId}
            onClose={() => setAgenticOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {/* Threads list */}
      {threads.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-10 text-center shadow-sm">
          <Mail className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium text-foreground">No outreach threads yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {threads.map((thread) => (
            <div
              key={thread.thread_id}
              className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="font-semibold text-foreground">{thread.subject}</h2>
                    <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${STATUS_COLORS[thread.status]}`}>
                      {STATUS_LABELS[thread.status]}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-4 text-sm text-muted-foreground">
                    <span>Contact: <span className="text-foreground">{thread.ia_contact}</span></span>
                    <span>{thread.message_count} messages</span>
                    <span>{new Date(thread.last_message_at).toLocaleDateString()}</span>
                  </div>
                  {thread.next_action && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Next: <span className="font-medium text-foreground">{thread.next_action}</span>
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setSendDialog({ open: true, threadId: thread.thread_id })}
                  className="flex items-center gap-2 rounded-xl border border-border/70 px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent"
                >
                  <Send className="h-4 w-4" />
                  Send Message
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Send Message Dialog */}
      {sendDialog.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation">
          <div className="w-full max-w-md rounded-2xl border border-border/70 bg-card p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="send-message-title">
            <h3 id="send-message-title" className="mb-4 text-lg font-semibold text-foreground">Send Message</h3>
            {sendSuccess ? (
              <div className="flex items-center gap-2 rounded-xl bg-primary/10 border border-primary/20 p-4">
                <CheckCircle2 className="h-5 w-5 text-primary" />
                <p className="text-sm font-medium text-primary">{sendSuccess}</p>
              </div>
            ) : (
              <>
                <textarea
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  placeholder="Type your message to IA West..."
                  rows={4}
                  className="w-full rounded-xl border border-border/70 bg-background px-4 py-3 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
                <div className="mt-4 flex gap-3">
                  <button
                    onClick={handleSend}
                    disabled={!messageText.trim()}
                    className="flex-1 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
                  >
                    Send
                  </button>
                  <button
                    onClick={() => setSendDialog({ open: false, threadId: null })}
                    className="flex-1 rounded-xl border border-border/70 py-2.5 text-sm font-medium text-foreground transition hover:bg-accent"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* New Thread Dialog */}
      {newThreadDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation">
          <div className="w-full max-w-md rounded-2xl border border-border/70 bg-card p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="new-thread-title">
            <h3 id="new-thread-title" className="mb-4 text-lg font-semibold text-foreground">New Outreach Thread</h3>
            {newThreadSuccess ? (
              <div className="flex items-center gap-2 rounded-xl bg-primary/10 border border-primary/20 p-4">
                <CheckCircle2 className="h-5 w-5 text-primary" />
                <p className="text-sm font-medium text-primary">Thread created! IA West will be in touch shortly.</p>
              </div>
            ) : (
              <>
                <div className="mb-4">
                  <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                    Event Name
                  </label>
                  <input
                    type="text"
                    value={newEventName}
                    onChange={(e) => setNewEventName(e.target.value)}
                    placeholder="e.g. Spring Tech Fair 2026"
                    className="w-full rounded-xl border border-border/70 bg-background px-4 py-3 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleNewThread}
                    disabled={!newEventName.trim()}
                    className="flex-1 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
                  >
                    Submit
                  </button>
                  <button
                    onClick={() => setNewThreadDialog(false)}
                    className="flex-1 rounded-xl border border-border/70 py-2.5 text-sm font-medium text-foreground transition hover:bg-accent"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
