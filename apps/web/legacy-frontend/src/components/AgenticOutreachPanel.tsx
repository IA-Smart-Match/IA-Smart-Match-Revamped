import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Sparkles, X } from "lucide-react";

export interface AgenticOutreachPanelProps {
  speakerName: string;
  eventName: string;
  coordinatorId?: string;
  eventDate?: string;
  onClose?: () => void;
}

interface MeetingSlot {
  slot_id: string;
  date: string;
  time: string;
  duration_minutes: number;
  meeting_link: string;
}

interface AgentState {
  agent_id: string;
  agent_name: string;
  role: string;
  step: number;
  status: "queued" | "running" | "done" | "error";
  output?: Record<string, unknown>;
  duration_ms?: number;
}

type WorkflowPhase = "idle" | "streaming" | "approval" | "approved" | "rejected";

const AGENT_ORDER = ["scout", "copywriter", "scheduler", "planner", "pipeline"];

export function AgenticOutreachPanel({
  speakerName,
  eventName,
  coordinatorId,
  eventDate,
  onClose,
}: AgenticOutreachPanelProps) {
  const [phase, setPhase] = useState<WorkflowPhase>("idle");
  const [agents, setAgents] = useState<Record<string, AgentState>>({});
  const [rejectReason, setRejectReason] = useState("");
  const [selectedSlot, setSelectedSlot] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPhase("streaming");

    (async () => {
      try {
        const res = await fetch("/api/outreach/agentic-workflow/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            speaker_name: speakerName,
            event_name: eventName,
            coordinator_id: coordinatorId,
            event_date: eventDate,
            request_source: "coordinator_portal",
            voice: "school_coordinator",
          }),
          signal: ctrl.signal,
        });

        if (!res.body) return;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const payload = JSON.parse(line.slice(6)) as Record<string, unknown>;
              const evt = payload.event as string;

              if (evt === "agent_queued") {
                const id = payload.agent_id as string;
                setAgents((prev) => ({
                  ...prev,
                  [id]: {
                    agent_id: id,
                    agent_name: payload.agent_name as string,
                    role: payload.role as string,
                    step: payload.step as number,
                    status: "queued",
                  },
                }));
              } else if (evt === "agent_running") {
                const id = payload.agent_id as string;
                setAgents((prev) => ({
                  ...prev,
                  [id]: { ...(prev[id] ?? { agent_id: id, agent_name: "", role: "", step: 0 }), status: "running" },
                }));
              } else if (evt === "agent_done") {
                const id = payload.agent_id as string;
                setAgents((prev) => ({
                  ...prev,
                  [id]: {
                    ...(prev[id] ?? { agent_id: id, agent_name: "", role: "", step: 0 }),
                    agent_name: (payload.agent_name as string) || prev[id]?.agent_name || "",
                    role: (payload.role as string) || prev[id]?.role || "",
                    step: (payload.step as number) ?? prev[id]?.step ?? 0,
                    status: "done",
                    output: payload.output as Record<string, unknown>,
                    duration_ms: payload.duration_ms as number,
                  },
                }));

                // Pre-select first slot when scheduler finishes
                if (id === "scheduler") {
                  const out = payload.output as Record<string, unknown> | undefined;
                  const slots = out?.proposed_slots as MeetingSlot[] | undefined;
                  if (slots?.[0]) setSelectedSlot(slots[0].slot_id);
                }
              } else if (evt === "workflow_complete") {
                setPhase("approval");
              }
            } catch {
              // Ignore malformed SSE lines
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setPhase("approval");
        }
      }
    })();

    return () => ctrl.abort();
  }, [speakerName, eventName, coordinatorId, eventDate]);

  const copywriterOutput = agents["copywriter"]?.output;
  const schedulerOutput = agents["scheduler"]?.output;
  const plannerOutput = agents["planner"]?.output;

  const emailSubject = (copywriterOutput?.subject as string) ?? "";
  const emailBody = (copywriterOutput?.email as string) ?? "";
  const slots = (schedulerOutput?.proposed_slots as MeetingSlot[]) ?? [];
  const checklist = (plannerOutput?.checklist as string[]) ?? [];

  const isStreaming = phase === "streaming";
  const isApproval = phase === "approval";

  return (
    <div className="flex flex-col gap-6">
      {/* Panel header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
            <Sparkles className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">AI Outreach Agents</h2>
            <p className="text-xs text-muted-foreground">
              {isStreaming ? (
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
                  Running…
                </span>
              ) : phase === "approval" ? (
                "Awaiting your approval"
              ) : phase === "approved" ? (
                "Outreach sent ✓"
              ) : phase === "rejected" ? (
                "Workflow cancelled"
              ) : (
                "Ready"
              )}
            </p>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-accent hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Agent rows */}
      <div className="space-y-2">
        {AGENT_ORDER.map((id, idx) => {
          const agent = agents[id];
          const stepLabel = idx + 1;

          if (!agent) {
            return (
              <div
                key={id}
                className="flex items-center gap-3 rounded-xl border border-border/50 bg-muted/30 px-4 py-3 opacity-40"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/60 text-xs text-muted-foreground">
                  {stepLabel}
                </span>
                <span className="text-sm text-muted-foreground">Waiting…</span>
              </div>
            );
          }

          return (
            <div
              key={id}
              className="flex items-center gap-3 rounded-xl border border-border/70 bg-card px-4 py-3 shadow-sm"
            >
              {agent.status === "running" ? (
                <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
              ) : agent.status === "done" ? (
                <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
              ) : agent.status === "error" ? (
                <AlertCircle className="h-5 w-5 shrink-0 text-destructive" />
              ) : (
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border/60 text-xs text-muted-foreground">
                  {stepLabel}
                </span>
              )}

              <div className="flex flex-1 flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{agent.agent_name}</span>
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {agent.role}
                </span>
              </div>

              {agent.status === "done" && agent.duration_ms != null && (
                <span className="text-xs text-muted-foreground">{agent.duration_ms}ms</span>
              )}
              {agent.status === "running" && (
                <span className="text-xs text-primary">Running…</span>
              )}
              {agent.status === "queued" && (
                <span className="text-xs text-muted-foreground">Queued</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Approval section */}
      {isApproval && phase !== "approved" && phase !== "rejected" && (
        <div className="space-y-5 rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <h3 className="text-base font-semibold text-foreground">Awaiting Your Approval</h3>

          {/* Email preview */}
          {emailSubject && (
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Email Subject</p>
              <div className="rounded-lg bg-muted/50 px-3 py-2 text-sm font-medium text-foreground">
                {emailSubject}
              </div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Message</p>
              <div className="max-h-40 overflow-y-auto rounded-lg bg-muted/50 px-3 py-2 text-sm text-foreground whitespace-pre-wrap">
                {emailBody}
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Voice: host school event coordinator inviting the volunteer — not IA West admin or chapter leadership.
              </p>
            </div>
          )}

          {/* Meeting slot picker */}
          {slots.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Choose Meeting Slot</p>
              <div className="space-y-1.5">
                {slots.map((slot) => (
                  <label
                    key={slot.slot_id}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition ${
                      selectedSlot === slot.slot_id
                        ? "border-primary bg-primary/5"
                        : "border-border/60 hover:bg-accent"
                    }`}
                  >
                    <input
                      type="radio"
                      name="meeting_slot"
                      value={slot.slot_id}
                      checked={selectedSlot === slot.slot_id}
                      onChange={() => setSelectedSlot(slot.slot_id)}
                      className="accent-primary"
                    />
                    <span className="text-sm text-foreground">
                      {slot.date} — {slot.time} ({slot.duration_minutes} min)
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Checklist preview */}
          {checklist.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Prep Checklist</p>
              <ul className="space-y-1">
                {checklist.map((item) => (
                  <li key={item} className="flex items-center gap-2 text-sm text-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-3 pt-1">
            <button
              onClick={() => setPhase("approved")}
              className="flex-1 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            >
              Approve &amp; Send
            </button>
            <button
              onClick={() => setPhase("rejected")}
              className="flex-1 rounded-xl border border-border/70 py-2.5 text-sm font-medium text-foreground transition hover:bg-accent"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {/* Approved state */}
      {phase === "approved" && (
        <div className="flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 p-4">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
          <p className="text-sm font-medium text-green-700">
            Outreach sent ✓ Pipeline updated — Speaker contacted successfully.
          </p>
        </div>
      )}

      {/* Rejected state */}
      {phase === "rejected" && (
        <div className="space-y-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <p className="text-sm font-medium text-foreground">Workflow cancelled.</p>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Reason (optional)
            </label>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={2}
              placeholder="e.g. Speaker unavailable for this event"
              className="w-full rounded-xl border border-border/70 bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-border/70 px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
