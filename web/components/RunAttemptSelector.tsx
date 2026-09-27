"use client";

import { useRouter } from "next/navigation";
import type { TrainingRun } from "../../shared/types";

function attemptLabel(run: TrainingRun): string {
  const status = run.status.toLowerCase().replace(/_/g, " ");
  return `Attempt ${run.attempt} — ${status}`;
}

/**
 * Attempt selector for jobs with more than one execution attempt.
 * Navigates with a `?run=` query param so the server component re-renders
 * the detail of the chosen run.
 */
export function RunAttemptSelector({
  projectId,
  jobId,
  runs,
  selectedRunId,
}: {
  projectId: string;
  jobId: string;
  runs: TrainingRun[];
  selectedRunId: string;
}) {
  const router = useRouter();

  if (runs.length < 2) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label
        htmlFor="run-attempt"
        className="text-sm font-semibold text-muted-ink"
      >
        Attempt
      </label>
      <select
        id="run-attempt"
        value={selectedRunId}
        onChange={(e) =>
          router.push(
            `/projects/${projectId}/jobs/${jobId}?run=${encodeURIComponent(e.target.value)}`,
          )
        }
        className="min-h-[44px] cursor-pointer rounded-lg border border-line bg-paper px-3 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal"
      >
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            {attemptLabel(run)}
          </option>
        ))}
      </select>
    </div>
  );
}
