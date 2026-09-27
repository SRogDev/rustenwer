"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { JobStatus } from "../../shared/types";
import { isApiOfflineError, transitionTrainingJob } from "../lib/api";

/**
 * Job lifecycle transition buttons (§42). Each action is only offered from
 * states it can legally leave; the API returns 409 on invalid transitions.
 */
const ACTIONS: { label: string; to: JobStatus; from: JobStatus[] }[] = [
  { label: "Queue", to: "QUEUED", from: ["CREATED", "FAILED"] },
  { label: "Run", to: "RUNNING", from: ["QUEUED"] },
  { label: "Pause", to: "PAUSED", from: ["RUNNING"] },
  { label: "Resume", to: "RUNNING", from: ["PAUSED"] },
  {
    label: "Cancel",
    to: "CANCELLED",
    from: ["CREATED", "QUEUED", "RUNNING", "PAUSED"],
  },
];

export function JobTransitionButtons({
  jobId,
  status,
}: {
  jobId: string;
  status: JobStatus;
}) {
  const router = useRouter();
  const [pending, setPending] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const available = ACTIONS.filter((a) => a.from.includes(status));
  if (available.length === 0) return null;

  async function handle(to: JobStatus) {
    setPending(to);
    setError(null);
    try {
      await transitionTrainingJob(jobId, to);
      router.refresh();
    } catch (err) {
      if (isApiOfflineError(err)) {
        setError("The API is offline, so the job cannot be transitioned.");
      } else {
        setError(err instanceof Error ? err.message : "Transition failed.");
      }
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {available.map((action) => (
        <button
          key={action.label}
          type="button"
          disabled={pending !== null}
          onClick={() => handle(action.to)}
          className="inline-flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-paper px-3 py-1.5 text-xs font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending === action.to && (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          )}
          {action.label}
        </button>
      ))}
      {error && (
        <p role="alert" className="w-full text-xs font-medium text-[#8f1d1d]">
          {error}
        </p>
      )}
    </div>
  );
}
