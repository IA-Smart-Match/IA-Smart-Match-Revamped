import { Check, Download, Loader2, Mail, Sparkles, X } from "lucide-react";
import { useNavigate } from "react-router";

import { type RankedMatch, type WorkflowResponse } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/app/components/ui/dialog";

interface OutreachWorkflowModalProps {
  volunteer: RankedMatch;
  result: WorkflowResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

const STEPS: { key: keyof WorkflowResponse["steps"]; label: string }[] = [
  { key: "email", label: "Generating outreach email..." },
  { key: "ics", label: "Creating calendar invite..." },
  { key: "pipeline", label: "Updating pipeline status..." },
];

export function OutreachWorkflowModal({
  volunteer,
  result,
  loading,
  error,
  onClose,
}: OutreachWorkflowModalProps) {
  const navigate = useNavigate();

  const handleDownloadIcs = () => {
    if (!result) return;
    const blob = new Blob([result.ics_content], { type: "text/calendar" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${volunteer.name.replace(/\s+/g, "-")}-invite.ics`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto rounded-xl p-8 sm:max-w-3xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
              <Mail className="w-5 h-5 text-primary" />
            </div>
            <div>
              <DialogTitle id="workflow-modal-title" className="text-2xl font-semibold text-foreground">
                Outreach Workflow
              </DialogTitle>
              <DialogDescription className="mt-1 text-sm text-muted-foreground">
                Review generated outreach steps for {volunteer.name} before you dispatch follow-up.
              </DialogDescription>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close workflow modal"
          >
            Close
          </button>
        </div>

        {/* Error banner */}
        {error ? (
          <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-destructive mb-4">
            {error}
          </div>
        ) : null}

        {/* 3-step checklist */}
        <div className="space-y-3 mb-6">
          {STEPS.map((step) => {
            if (loading) {
              return (
                <div key={step.key} className="flex items-center gap-3 text-foreground">
                  <Loader2 className="w-5 h-5 animate-spin text-primary flex-shrink-0" />
                  <span>{step.label}</span>
                </div>
              );
            }

            if (!result) return null;

            const stepResult = result.steps[step.key];
            const isOk = stepResult.status === "ok";

            return (
              <div key={step.key} className="flex items-start gap-3">
                {isOk ? (
                  <Check className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                ) : (
                  <X className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
                )}
                <div>
                  <span className="text-foreground">
                    {step.label}
                  </span>
                  {!isOk && stepResult.error ? (
                    <p className="text-sm text-destructive mt-1">{stepResult.error}</p>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>

        {/* Email content (shown after success) */}
        {result ? (
          <div className="space-y-4">
            {result.steps.email.status === "ok" ? (
              <>
                <div>
                  <p className="text-sm font-medium text-foreground mb-2">Subject</p>
                  <div className="rounded-lg bg-muted px-4 py-3 text-foreground">
                    {result.email_data.subject_line}
                  </div>
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground mb-2">Message</p>
                  <div className="rounded-lg bg-muted px-4 py-3 text-foreground whitespace-pre-wrap min-h-[240px]">
                    {result.email}
                  </div>
                </div>
              </>
            ) : null}

            {/* ICS download button */}
            {result.steps.ics.status === "ok" ? (
              <button
                onClick={handleDownloadIcs}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
              >
                <Download className="w-4 h-4" /> Download Calendar Invite
              </button>
            ) : null}

            {/* Pipeline status badge */}
            {result.pipeline_updated ? (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-primary/10 text-primary rounded-full text-sm font-medium">
                <Check className="w-4 h-4" />
                Pipeline Updated: Contacted
              </div>
            ) : result.steps.pipeline.status === "error" ? (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-destructive/10 text-destructive rounded-full text-sm font-medium">
                <X className="w-4 h-4" />
                Pipeline Update Failed
              </div>
            ) : null}

            {/* Upgrade to Agentic */}
            <div className="mt-2 border-t border-border/60 pt-4">
              <button
                onClick={() => {
                  onClose();
                  navigate("/coordinator-portal/outreach");
                }}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-primary/40 bg-primary/5 px-4 py-2.5 text-sm font-semibold text-primary transition hover:bg-primary/10"
              >
                <Sparkles className="w-4 h-4" />
                Upgrade to Agentic — Launch AI Outreach Agents
              </button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
