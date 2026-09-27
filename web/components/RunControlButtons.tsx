"use client";

import { Info, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { CheckpointInfo, JobStatus } from "../../shared/types";
import {
  cancelRun,
  type EnqueueRunInput,
  enqueueTrainingJob,
  isApiOfflineError,
  pauseRun,
  resumeRun,
  retryRun,
  type TrainingProvider,
} from "../lib/api";

type Action = "enqueue" | "pause" | "resume" | "cancel" | "retry";

const BUTTON_STYLES =
  "inline-flex min-h-[44px] cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-paper px-4 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum disabled:cursor-not-allowed disabled:opacity-60";

const PRIMARY_STYLES =
  "inline-flex min-h-[44px] cursor-pointer items-center gap-1.5 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-platinum transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60";

const TERMINAL_STATUSES: JobStatus[] = ["FAILED", "CANCELLED", "COMPLETED"];

/**
 * Run lifecycle controls for a training job (Phase 2 executor).
 * Pause/Resume/Cancel/Retry are only offered from legal run states, mirroring
 * JobTransitionButtons; the Enqueue form starts a new attempt (optionally
 * from a checkpoint). API 409 details are shown inline.
 */
export function RunControlButtons({
  jobId,
  runId,
  runStatus,
  checkpoints,
  canEnqueue,
  hasStrategy,
}: {
  jobId: string;
  runId: string | null;
  runStatus: JobStatus | null;
  checkpoints: CheckpointInfo[];
  canEnqueue: boolean;
  hasStrategy: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState<TrainingProvider>("local");
  const [hyperparameters, setHyperparameters] = useState("");
  const [checkpointId, setCheckpointId] = useState("");

  const canPause = runStatus === "RUNNING";
  const canResume = runStatus === "PAUSED";
  const canCancel =
    runId !== null &&
    (runStatus === "QUEUED" ||
      runStatus === "RUNNING" ||
      runStatus === "PAUSED");
  const canRetry =
    runId !== null && (runStatus === "FAILED" || runStatus === "CANCELLED");
  const showActions = canPause || canResume || canCancel || canRetry;

  async function runAction(action: Action, fn: () => Promise<unknown>) {
    setPending(action);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (err) {
      if (isApiOfflineError(err)) {
        setError("The API is offline, so the run cannot be changed.");
      } else {
        setError(err instanceof Error ? err.message : "Action failed.");
      }
    } finally {
      setPending(null);
    }
  }

  function parseHyperparameters(): Record<string, unknown> | null {
    const trimmed = hyperparameters.trim();
    if (trimmed === "") return {};
    try {
      const value: unknown = JSON.parse(trimmed);
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new Error("not an object");
      }
      return value as Record<string, unknown>;
    } catch {
      setError(
        'Hyperparameters must be a JSON object, e.g. {"learning_rate": 0.0002}.',
      );
      return null;
    }
  }

  function handleEnqueue() {
    setError(null);
    const parsed = parseHyperparameters();
    if (parsed === null) return;
    const input: EnqueueRunInput = { provider };
    if (Object.keys(parsed).length > 0) input.hyperparameters = parsed;
    if (checkpointId !== "") input.resume_from_checkpoint_id = checkpointId;
    void runAction("enqueue", () => enqueueTrainingJob(jobId, input));
  }

  return (
    <div className="space-y-4">
      {showActions && (
        <div className="flex flex-wrap items-center gap-2">
          {canPause && (
            <button
              type="button"
              disabled={pending !== null}
              onClick={() =>
                runAction("pause", () => pauseRun(jobId, runId ?? ""))
              }
              className={BUTTON_STYLES}
            >
              {pending === "pause" && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Pause
            </button>
          )}
          {canResume && (
            <button
              type="button"
              disabled={pending !== null}
              onClick={() =>
                runAction("resume", () => resumeRun(jobId, runId ?? ""))
              }
              className={BUTTON_STYLES}
            >
              {pending === "resume" && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Resume
            </button>
          )}
          {canCancel && (
            <button
              type="button"
              disabled={pending !== null}
              onClick={() =>
                runAction("cancel", () => cancelRun(jobId, runId ?? ""))
              }
              className={BUTTON_STYLES}
            >
              {pending === "cancel" && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Cancel
            </button>
          )}
          {canRetry && (
            <button
              type="button"
              disabled={pending !== null}
              onClick={() =>
                runAction("retry", () =>
                  retryRun(jobId, runId ?? "", { from_checkpoint: false }),
                )
              }
              className={BUTTON_STYLES}
            >
              {pending === "retry" && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Retry
            </button>
          )}
        </div>
      )}

      {canEnqueue && (
        <form
          className="rounded-xl border border-line bg-card p-5"
          onSubmit={(e) => {
            e.preventDefault();
            handleEnqueue();
          }}
        >
          <h3 className="font-display text-base font-bold text-charcoal">
            {runId === null ? "Enqueue the first run" : "Enqueue a new attempt"}
          </h3>
          {!hasStrategy && (
            <p className="mt-2 flex items-start gap-2 text-sm text-[#8f1d1d]">
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              This job has no training strategy yet, so the API will reject the
              enqueue with a 409.
            </p>
          )}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="enqueue-provider"
                className="block text-sm font-semibold text-charcoal"
              >
                Provider
              </label>
              <select
                id="enqueue-provider"
                value={provider}
                onChange={(e) =>
                  setProvider(e.target.value as TrainingProvider)
                }
                className="mt-1 min-h-[44px] w-full cursor-pointer rounded-lg border border-line bg-paper px-3 py-2 text-sm text-charcoal"
              >
                <option value="local">local</option>
                <option value="digitalocean">digitalocean</option>
              </select>
              <p className="mt-1 text-xs text-muted-ink">
                DigitalOcean runs require a DO_API_TOKEN configured on the
                backend.
              </p>
            </div>
            <div>
              <label
                htmlFor="enqueue-checkpoint"
                className="block text-sm font-semibold text-charcoal"
              >
                Resume from checkpoint
              </label>
              <select
                id="enqueue-checkpoint"
                value={checkpointId}
                onChange={(e) => setCheckpointId(e.target.value)}
                className="mt-1 min-h-[44px] w-full cursor-pointer rounded-lg border border-line bg-paper px-3 py-2 text-sm text-charcoal"
              >
                <option value="">None — train from scratch</option>
                {checkpoints.map((ckpt) => (
                  <option key={ckpt.id} value={ckpt.id}>
                    {ckpt.id} (epoch {ckpt.epoch}, step {ckpt.step})
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-muted-ink">
                Resuming starts a new attempt initialized from that checkpoint.
              </p>
            </div>
          </div>
          <div className="mt-4">
            <label
              htmlFor="enqueue-hyperparameters"
              className="block text-sm font-semibold text-charcoal"
            >
              Hyperparameter overrides{" "}
              <span className="font-normal text-muted-ink">
                (optional JSON)
              </span>
            </label>
            <textarea
              id="enqueue-hyperparameters"
              value={hyperparameters}
              onChange={(e) => setHyperparameters(e.target.value)}
              placeholder='{"learning_rate": 0.0002, "epochs": 5}'
              rows={3}
              spellCheck={false}
              className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 font-mono text-sm text-charcoal placeholder:text-muted-ink/60"
            />
          </div>
          <button
            type="submit"
            disabled={pending !== null}
            className={`${PRIMARY_STYLES} mt-4`}
          >
            {pending === "enqueue" && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Enqueue run
          </button>
        </form>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-[#DC2626]/30 bg-[#DC2626]/10 px-4 py-3 text-sm font-medium text-[#8f1d1d]"
        >
          {error}
        </p>
      )}

      {!showActions && !canEnqueue && runStatus !== null && (
        <p className="text-sm text-muted-ink">
          {TERMINAL_STATUSES.includes(runStatus)
            ? "This attempt is finished. Enqueue a new attempt to train again."
            : "No actions available for this run state."}
        </p>
      )}
    </div>
  );
}
