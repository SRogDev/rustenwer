"use client";

import { Ban, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { EvaluationRun, EvaluationStatus } from "../../shared/types";
import {
  cancelEvaluationRun,
  getEvaluationRun,
  isApiOfflineError,
} from "../lib/api";
import { BUTTON_DANGER, ERROR_STYLES } from "./formStyles";
import { QualityVectorRadar } from "./QualityVectorRadar";
import { StatusPill } from "./StatusPill";

const TERMINAL_STATUSES: EvaluationStatus[] = [
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];
const POLL_MS = 3000;

function formatDateTime(iso: string | null): string {
  if (iso === null) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatScalar(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatSubject(run: EvaluationRun): string {
  const ref = run.subject.ref ?? "—";
  return `${run.subject.kind} · ${ref}`;
}

const COST_DIMENSIONS: {
  key:
    | "latency_ms_p50"
    | "latency_ms_p99"
    | "inference_cost_usd_per_1k"
    | "training_cost_usd"
    | "model_size_bytes";
  label: string;
  format: (v: number) => string;
}[] = [
  { key: "latency_ms_p50", label: "Latency p50", format: (v) => `${v} ms` },
  { key: "latency_ms_p99", label: "Latency p99", format: (v) => `${v} ms` },
  {
    key: "inference_cost_usd_per_1k",
    label: "Inference cost / 1k",
    format: (v) => `$${v.toFixed(6)}`,
  },
  {
    key: "training_cost_usd",
    label: "Training cost",
    format: (v) => `$${v.toFixed(2)}`,
  },
  {
    key: "model_size_bytes",
    label: "Model size",
    format: (v) => (v < 1024 ? `${v} B` : `${(v / 1024 / 1024).toFixed(1)} MB`),
  },
];

/**
 * Evaluation run detail (Phase 3).
 * Polls GET /evaluation-runs/{run_id} every 3s while the run is non-terminal,
 * offers Cancel while PENDING/RUNNING, and renders the quality vector as an
 * SVG radar plus cost dimensions, raw metrics, cost and any failure error.
 */
export function EvaluationRunDetail({
  initial,
  backHref,
}: {
  initial: EvaluationRun;
  backHref: string;
}) {
  const router = useRouter();
  const [run, setRun] = useState<EvaluationRun>(initial);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchRun() {
      try {
        const data = await getEvaluationRun(initial.id);
        if (!cancelled) {
          setRun(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && !isApiOfflineError(err)) {
          setError(
            err instanceof Error ? err.message : "Could not refresh the run.",
          );
        }
      }
    }
    if (TERMINAL_STATUSES.includes(run.status))
      return () => {
        cancelled = true;
      };
    const timer = setInterval(() => void fetchRun(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [initial.id, run.status]);

  async function handleCancel() {
    setCancelling(true);
    setError(null);
    try {
      const updated = await cancelEvaluationRun(run.id);
      setRun(updated);
      router.refresh();
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so the run cannot be cancelled."
          : err instanceof Error
            ? err.message
            : "Could not cancel the run.",
      );
    } finally {
      setCancelling(false);
    }
  }

  const canCancel = run.status === "PENDING" || run.status === "RUNNING";
  const metricEntries = Object.entries(run.metrics ?? {});
  const qualityVector = run.quality_vector;

  return (
    <div className="space-y-6">
      {error && (
        <p role="alert" className={ERROR_STYLES}>
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <StatusPill status={run.status} />
        {canCancel && (
          <button
            type="button"
            onClick={handleCancel}
            disabled={cancelling}
            className={BUTTON_DANGER}
          >
            {cancelling ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Ban className="h-4 w-4" aria-hidden="true" />
            )}
            {cancelling ? "Cancelling…" : "Cancel run"}
          </button>
        )}
      </div>

      {run.status === "FAILED" && run.error && (
        <div
          role="alert"
          className="rounded-xl border border-[#DC2626]/30 bg-[#DC2626]/10 p-5"
        >
          <h2 className="font-display text-base font-bold text-[#8f1d1d]">
            Run failed
          </h2>
          <p className="mt-2 font-mono text-sm break-words text-[#8f1d1d]">
            {run.error}
          </p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-line bg-card p-5">
          <h2 className="font-display text-base font-bold text-charcoal">
            Quality vector
          </h2>
          {qualityVector ? (
            <>
              <div className="mt-3 flex justify-center">
                <QualityVectorRadar vector={qualityVector} />
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 text-sm sm:grid-cols-3">
                {COST_DIMENSIONS.map((dim) => {
                  const value = qualityVector[dim.key];
                  return (
                    <div key={dim.key}>
                      <dt className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                        {dim.label}
                      </dt>
                      <dd className="mt-0.5 font-semibold text-charcoal">
                        {typeof value === "number" ? dim.format(value) : "—"}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </>
          ) : (
            <p className="mt-3 text-sm text-muted-ink">
              No quality vector yet — it appears here once the run finishes
              evaluating.
            </p>
          )}
        </div>

        <div className="rounded-xl border border-line bg-card p-5">
          <h2 className="font-display text-base font-bold text-charcoal">
            Run details
          </h2>
          <dl className="mt-3 space-y-3 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="font-semibold text-muted-ink">Subject</dt>
              <dd className="font-mono text-[13px] break-all text-charcoal">
                {formatSubject(run)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="font-semibold text-muted-ink">Cost</dt>
              <dd className="text-charcoal">${run.cost_usd.toFixed(4)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="font-semibold text-muted-ink">Created</dt>
              <dd className="text-charcoal">
                {formatDateTime(run.created_at)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="font-semibold text-muted-ink">Completed</dt>
              <dd className="text-charcoal">
                {formatDateTime(run.completed_at)}
              </dd>
            </div>
          </dl>

          <h3 className="mt-6 font-display text-sm font-bold text-charcoal">
            Metrics
          </h3>
          {metricEntries.length === 0 ? (
            <p className="mt-2 text-sm text-muted-ink">
              No metrics recorded for this run.
            </p>
          ) : (
            <dl className="mt-2 overflow-hidden rounded-lg border border-line text-sm">
              {metricEntries.map(([key, value], i) => (
                <div
                  key={key}
                  className={`flex justify-between gap-3 px-3 py-2 ${i % 2 === 0 ? "bg-platinum/30" : "bg-card"}`}
                >
                  <dt className="font-mono text-[13px] text-muted-ink">
                    {key}
                  </dt>
                  <dd className="font-semibold break-all text-charcoal">
                    {formatScalar(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>

      <Link
        href={backHref}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-line bg-card px-4 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
      >
        Back to benchmark
      </Link>
    </div>
  );
}
