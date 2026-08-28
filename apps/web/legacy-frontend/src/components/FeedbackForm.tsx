import { useState } from "react";
import { AlertCircle, CheckCircle2, MessageSquareHeart, Send } from "lucide-react";

import {
  emptyFeedbackStatsSummary,
  fetchFeedbackStats,
  submitFeedback,
  type FactorWeights,
  type FeedbackStatsSummary,
  type FeedbackWeightSnapshot,
} from "@/lib/api";

type FeedbackFormProps = {
  eventName: string;
  speakerName: string;
  matchScore?: number;
  factorScores?: Record<string, number>;
  weightsUsed?: FactorWeights;
  currentStats?: FeedbackStatsSummary;
  onSubmitted?: (stats: FeedbackStatsSummary) => void | Promise<void>;
  onCancel?: () => void;
  title?: string;
  description?: string;
  className?: string;
};

const declineReasons = [
  "Too far (geographic distance)",
  "Schedule conflict",
  "Topic mismatch",
  "Speaker already committed",
  "Other",
] as const;

const positiveOutcomes = [
  { value: "accepted", label: "Accepted" },
  { value: "attended", label: "Attended" },
  { value: "follow_up_pending", label: "Follow-up pending" },
  { value: "no_show", label: "No-show" },
] as const;

function mergeSnapshotIntoStats(
  currentStats: FeedbackStatsSummary | undefined,
  snapshot: FeedbackWeightSnapshot,
): FeedbackStatsSummary {
  const baseline = currentStats ?? emptyFeedbackStatsSummary();
  const nextHistory = [...baseline.weight_history.filter((entry) => entry.timestamp !== snapshot.timestamp), snapshot]
    .sort((left, right) => left.timestamp.localeCompare(right.timestamp))
    .slice(-8);

  return {
    ...baseline,
    total_feedback: snapshot.total_feedback,
    accepted: snapshot.accepted,
    declined: snapshot.declined,
    acceptance_rate: snapshot.acceptance_rate,
    pain_score: snapshot.pain_score,
    default_weights:
      Object.keys(baseline.default_weights).length > 0
        ? baseline.default_weights
        : snapshot.baseline_weights,
    current_weights: snapshot.weights,
    suggested_weights: snapshot.weights,
    recommended_adjustments: snapshot.adjustments,
    weight_history: nextHistory,
  };
}

export function FeedbackForm({
  eventName,
  speakerName,
  matchScore = 0,
  factorScores = {},
  weightsUsed,
  currentStats,
  onSubmitted,
  onCancel,
  title = "Record Feedback",
  description = "Capture the coordinator outcome so the optimizer can learn from real match decisions.",
  className = "",
}: FeedbackFormProps) {
  const [decision, setDecision] = useState<"accept" | "decline">("accept");
  const [declineReason, setDeclineReason] = useState<(typeof declineReasons)[number]>("Topic mismatch");
  const [declineNotes, setDeclineNotes] = useState("");
  const [eventOutcome, setEventOutcome] = useState<(typeof positiveOutcomes)[number]["value"]>("accepted");
  const [membershipInterest, setMembershipInterest] = useState(false);
  const [coordinatorRating, setCoordinatorRating] = useState("4");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const submission = await submitFeedback({
        event_name: eventName,
        speaker_name: speakerName,
        decision,
        match_score: matchScore,
        decline_reason: decision === "decline" ? declineReason : undefined,
        decline_notes: decision === "decline" ? declineNotes : undefined,
        event_outcome: decision === "decline" ? "declined" : eventOutcome,
        membership_interest: decision === "accept" ? membershipInterest : false,
        coordinator_rating: Number(coordinatorRating),
        factor_scores: factorScores,
        weights_used: weightsUsed,
      });
      let stats = mergeSnapshotIntoStats(currentStats, submission.optimizer_snapshot);

      try {
        const refreshResult = await fetchFeedbackStats();
        stats = refreshResult.data;
        setSuccess("Feedback recorded and optimizer metrics refreshed.");
      } catch {
        setSuccess(
          "Feedback recorded. Live stats refresh failed, so the latest optimizer snapshot is shown instead.",
        );
      }

      if (onSubmitted) {
        await onSubmitted(stats);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to submit feedback.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className={`rounded-3xl border border-slate-200 bg-white p-6 shadow-sm ${className}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-100 text-blue-700">
              <MessageSquareHeart className="h-5 w-5" />
            </span>
            <div>
              <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
              <p className="text-sm text-slate-600">{description}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Event</p>
          <p className="mt-1 font-semibold text-slate-900">{eventName}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Volunteer</p>
          <p className="mt-1 font-semibold text-slate-900">{speakerName}</p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div>
          <label className="mb-2 block text-sm font-medium text-slate-700">Decision</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setDecision("accept")}
              className={`rounded-2xl border px-4 py-3 text-sm font-medium ${
                decision === "accept"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              Accept
            </button>
            <button
              type="button"
              onClick={() => setDecision("decline")}
              className={`rounded-2xl border px-4 py-3 text-sm font-medium ${
                decision === "decline"
                  ? "border-rose-200 bg-rose-50 text-rose-700"
                  : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              Decline
            </button>
          </div>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-slate-700">
            Coordinator rating
          </label>
          <select
            value={coordinatorRating}
            onChange={(event) => setCoordinatorRating(event.target.value)}
            className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          >
            {["5", "4", "3", "2", "1"].map((rating) => (
              <option key={rating} value={rating}>
                {rating} / 5
              </option>
            ))}
          </select>
        </div>
      </div>

      {decision === "decline" ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Decline reason</label>
            <select
              value={declineReason}
              onChange={(event) =>
                setDeclineReason(event.target.value as (typeof declineReasons)[number])
              }
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            >
              {declineReasons.map((reason) => (
                <option key={reason} value={reason}>
                  {reason}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Notes</label>
            <textarea
              value={declineNotes}
              onChange={(event) => setDeclineNotes(event.target.value)}
              rows={3}
              placeholder="Add any context leadership would want later."
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
          </div>
        </div>
      ) : (
        <div className="mt-5 grid gap-4 md:grid-cols-[1fr_auto]">
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Outcome stage</label>
            <select
              value={eventOutcome}
              onChange={(event) =>
                setEventOutcome(event.target.value as (typeof positiveOutcomes)[number]["value"])
              }
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            >
              {positiveOutcomes.map((outcome) => (
                <option key={outcome.value} value={outcome.value}>
                  {outcome.label}
                </option>
              ))}
            </select>
          </div>
          <label className="mt-8 inline-flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={membershipInterest}
              onChange={(event) => setMembershipInterest(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Membership interest captured
          </label>
        </div>
      )}

      <div className="mt-5 rounded-2xl border border-blue-100 bg-blue-50/70 px-4 py-3">
        <p className="text-xs uppercase tracking-[0.18em] text-blue-700">Submission context</p>
        <p className="mt-1 text-sm text-slate-700">
          Match score at submission: <span className="font-semibold">{Math.round(matchScore * 100)}%</span>
        </p>
      </div>

      {error ? (
        <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        </div>
      ) : null}

      {success ? (
        <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{success}</span>
          </div>
        </div>
      ) : null}

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={submitting}
          className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Send className="h-4 w-4" />
          {submitting ? "Submitting..." : "Submit Feedback"}
        </button>
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-2xl border border-slate-300 px-5 py-3 font-medium text-slate-700 transition hover:bg-slate-50"
          >
            Cancel
          </button>
        ) : null}
      </div>
    </section>
  );
}
