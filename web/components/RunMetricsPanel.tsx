"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { JobStatus, MetricSeries, RunMetrics } from "../../shared/types";
import { getRunMetrics, isApiOfflineError } from "../lib/api";

const TERMINAL_STATUSES: JobStatus[] = ["FAILED", "CANCELLED", "COMPLETED"];
const POLL_MS = 3000;

const CHART_W = 600;
const CHART_H = 260;
const PAD = { left: 52, right: 16, top: 16, bottom: 32 };

function formatValue(key: string, value: number): string {
  if (key === "epoch" || key === "step") return String(Math.round(value));
  if (
    (key === "lr" || key === "learning_rate") &&
    value !== 0 &&
    Math.abs(value) < 0.01
  ) {
    return value.toExponential(1);
  }
  return Math.abs(value) < 10 ? value.toFixed(4) : value.toFixed(2);
}

const STAT_KEYS: { key: string; label: string }[] = [
  { key: "loss", label: "Loss" },
  { key: "lr", label: "Learning rate" },
  { key: "learning_rate", label: "Learning rate" },
  { key: "grad_norm", label: "Grad norm" },
  { key: "epoch", label: "Epoch" },
  { key: "step", label: "Step" },
];

/**
 * Inline SVG line chart for one metric series. Hand-rolled (no chart
 * dependencies): a polyline over the step range with a linear/log Y toggle.
 */
function LossChart({
  series,
  logScale,
}: {
  series: MetricSeries;
  logScale: boolean;
}) {
  const points = series.points;
  if (points.length === 0) return null;

  const first = points[0];
  if (!first) return null;

  const scaled = points.map((p) =>
    logScale ? Math.log10(Math.max(p.value, 1e-12)) : p.value,
  );
  const rawValues = points.map((p) => p.value);
  const steps = points.map((p) => p.step);
  const minY = Math.min(...scaled);
  const maxY = Math.max(...scaled);
  const minRaw = Math.min(...rawValues);
  const maxRaw = Math.max(...rawValues);
  const minStep = Math.min(...steps);
  const maxStep = Math.max(...steps);
  const spanY = maxY - minY || 1;
  const spanStep = maxStep - minStep || 1;

  const plotW = CHART_W - PAD.left - PAD.right;
  const plotH = CHART_H - PAD.top - PAD.bottom;
  const x = (step: number) => PAD.left + ((step - minStep) / spanStep) * plotW;
  const y = (v: number) => PAD.top + (1 - (v - minY) / spanY) * plotH;

  const line = points
    .map((p, i) => `${x(p.step).toFixed(1)},${y(scaled[i] ?? minY).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${CHART_W} ${CHART_H}`}
      role="img"
      aria-label={`${series.name} over training steps${logScale ? " (log scale)" : ""}`}
      className="h-auto w-full"
    >
      <line
        x1={PAD.left}
        y1={CHART_H - PAD.bottom}
        x2={CHART_W - PAD.right}
        y2={CHART_H - PAD.bottom}
        stroke="#d9d7d3"
        strokeWidth={1}
      />
      <line
        x1={PAD.left}
        y1={PAD.top}
        x2={PAD.left}
        y2={CHART_H - PAD.bottom}
        stroke="#d9d7d3"
        strokeWidth={1}
      />
      <polyline
        points={line}
        fill="none"
        stroke="#16161a"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <text
        x={PAD.left - 8}
        y={PAD.top + 4}
        textAnchor="end"
        fontSize={11}
        fill="#4b4b52"
      >
        {formatValue(series.name, maxRaw)}
      </text>
      <text
        x={PAD.left - 8}
        y={CHART_H - PAD.bottom}
        textAnchor="end"
        fontSize={11}
        fill="#4b4b52"
      >
        {formatValue(series.name, minRaw)}
      </text>
      <text
        x={PAD.left}
        y={CHART_H - 10}
        textAnchor="start"
        fontSize={11}
        fill="#4b4b52"
      >
        step {minStep}
      </text>
      <text
        x={CHART_W - PAD.right}
        y={CHART_H - 10}
        textAnchor="end"
        fontSize={11}
        fill="#4b4b52"
      >
        step {maxStep}
      </text>
    </svg>
  );
}

/**
 * Metrics panel: latest-value stat cards plus a loss chart.
 * Polls GET …/metrics every 3s while the run is non-terminal.
 */
export function RunMetricsPanel({
  jobId,
  runId,
  runStatus,
}: {
  jobId: string;
  runId: string;
  runStatus: JobStatus;
}) {
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  const [logScale, setLogScale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function fetchMetrics() {
      try {
        const data = await getRunMetrics(jobId, runId);
        if (!cancelled) {
          setMetrics(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setLoading(false);
          setError(
            isApiOfflineError(err)
              ? "The API is offline, so metrics cannot be loaded."
              : err instanceof Error
                ? err.message
                : "Could not load metrics.",
          );
        }
      }
    }
    void fetchMetrics();
    if (TERMINAL_STATUSES.includes(runStatus))
      return () => {
        cancelled = true;
      };
    const timer = setInterval(() => void fetchMetrics(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobId, runId, runStatus]);

  const lossSeries =
    metrics?.series.find((s) => s.name === "loss") ??
    metrics?.series[0] ??
    null;

  const statCards = STAT_KEYS.filter(
    (entry, index, arr) =>
      metrics !== null &&
      entry.key in metrics.latest &&
      arr.findIndex((e) => e.key === entry.key) === index,
  ).slice(0, 6);

  return (
    <div className="space-y-4">
      {loading && (
        <p className="flex items-center gap-2 text-sm text-muted-ink">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading metrics…
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm font-medium text-[#8f1d1d]">
          {error}
        </p>
      )}

      {statCards.length > 0 && metrics && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {statCards.map((entry) => (
            <div
              key={entry.key}
              className="rounded-xl border border-line bg-card p-4"
            >
              <dt className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                {entry.label}
              </dt>
              <dd className="mt-1 font-display text-xl font-bold text-charcoal">
                {formatValue(entry.key, metrics.latest[entry.key] ?? 0)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {lossSeries && lossSeries.points.length > 0 ? (
        <div className="rounded-xl border border-line bg-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-display text-base font-bold text-charcoal">
              {lossSeries.name}
            </h3>
            <fieldset className="flex overflow-hidden rounded-lg border border-line">
              <legend className="sr-only">Y-axis scale</legend>
              {[
                { value: false, label: "Linear" },
                { value: true, label: "Log" },
              ].map((option) => (
                <button
                  key={option.label}
                  type="button"
                  aria-pressed={logScale === option.value}
                  onClick={() => setLogScale(option.value)}
                  className={`min-h-[36px] cursor-pointer px-3 py-1 text-xs font-semibold transition-colors duration-200 ${
                    logScale === option.value
                      ? "bg-charcoal text-platinum"
                      : "bg-paper text-charcoal hover:bg-platinum"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </fieldset>
          </div>
          <div className="mt-3">
            <LossChart series={lossSeries} logScale={logScale} />
          </div>
        </div>
      ) : (
        !loading &&
        !error && (
          <div className="rounded-xl border border-dashed border-line bg-card p-8 text-center">
            <p className="text-sm text-muted-ink">
              No metrics yet — they appear here once the run starts emitting
              them.
            </p>
          </div>
        )
      )}
    </div>
  );
}
