"use client";

import { GitCompareArrows, Loader2 } from "lucide-react";
import { useState } from "react";
import type {
  ComparisonReport,
  ComparisonSubjectResult,
  EvaluationRun,
  QualityVector,
} from "../../shared/types";
import {
  type CompareSubjectInput,
  compareBenchmark,
  isApiOfflineError,
} from "../lib/api";
import {
  BUTTON_PRIMARY,
  ERROR_STYLES,
  HINT_STYLES,
  INPUT_STYLES,
  LABEL_STYLES,
} from "./formStyles";
import { StatusPill } from "./StatusPill";

const QUALITY_ROWS: { key: keyof QualityVector; label: string }[] = [
  { key: "task_quality", label: "Task quality" },
  { key: "calibration", label: "Calibration" },
  { key: "robustness", label: "Robustness" },
  { key: "reliability", label: "Reliability" },
  { key: "latency_ms_p50", label: "Latency p50 (ms)" },
  { key: "latency_ms_p99", label: "Latency p99 (ms)" },
  { key: "inference_cost_usd_per_1k", label: "Inference $ / 1k" },
  { key: "training_cost_usd", label: "Training $" },
];

function formatQv(value: number | null): string {
  if (value === null) return "—";
  return Math.abs(value) < 10 ? value.toFixed(4) : value.toFixed(2);
}

function subjectLabel(run: EvaluationRun): string {
  return `${run.name} (${run.subject.kind} · ${run.subject.ref ?? "—"})`;
}

/**
 * Stable React key for a comparison column. A comparison never contains the
 * same subject twice (run selection is by unique run id), so kind+ref
 * identifies a column.
 */
function resultKey(result: ComparisonSubjectResult, prefix = ""): string {
  return `${prefix}${result.subject.kind}|${result.subject.ref ?? "none"}|${String(result.beats_bar)}|${String(result.beats_incumbent)}`;
}

/**
 * Compare panel (Phase 3).
 * Multi-subject select over the benchmark's evaluation runs plus freeform
 * baseline names; calls POST …/compare and renders the ComparisonReport as
 * a side-by-side quality-vector table with beats badges and a winner
 * highlight.
 */
export function ComparePanel({
  benchmarkId,
  runs,
}: {
  benchmarkId: string;
  runs: EvaluationRun[];
}) {
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [baselineNames, setBaselineNames] = useState("");
  const [incumbentVersionId, setIncumbentVersionId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ComparisonReport | null>(null);

  const completedRuns = runs.filter((r) => r.status === "COMPLETED");

  function toggleRun(id: string) {
    setSelectedRunIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  const extraSubjects: CompareSubjectInput[] = baselineNames
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s !== "")
    .map((name) => ({ kind: "baseline" as const, ref: name }));

  const canCompare =
    !comparing && selectedRunIds.length + extraSubjects.length >= 2;

  async function handleCompare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCompare) return;
    setComparing(true);
    setError(null);
    try {
      const subjects: CompareSubjectInput[] = [
        ...selectedRunIds
          .map((id) => runs.find((r) => r.id === id))
          .filter((r): r is EvaluationRun => r !== undefined)
          .map((r) => ({ kind: r.subject.kind, ref: r.subject.ref })),
        ...extraSubjects,
      ];
      const result = await compareBenchmark(benchmarkId, {
        subjects,
        incumbent_intelligence_version_id:
          incumbentVersionId.trim() === "" ? null : incumbentVersionId.trim(),
      });
      setReport(result);
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so the comparison cannot be run."
          : err instanceof Error
            ? err.message
            : "Could not run the comparison.",
      );
    } finally {
      setComparing(false);
    }
  }

  const winnerIdx =
    report === null || report.winner === null
      ? -1
      : report.results.findIndex((r) => r.subject.ref === report.winner);

  return (
    <div className="rounded-xl border border-line bg-card p-5">
      <h2 className="font-display text-base font-bold text-charcoal">
        Compare subjects
      </h2>
      <p className="mt-1 text-sm text-muted-ink">
        Select at least two subjects to compare their quality vectors
        side-by-side.
      </p>

      {error && (
        <p role="alert" className={`${ERROR_STYLES} mt-4`}>
          {error}
        </p>
      )}

      <form onSubmit={handleCompare} className="mt-4">
        <fieldset>
          <legend className={LABEL_STYLES}>Evaluation runs</legend>
          {completedRuns.length === 0 ? (
            <p className="text-sm text-muted-ink">
              No completed runs on this benchmark yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {completedRuns.map((run) => {
                const checked = selectedRunIds.includes(run.id);
                return (
                  <li key={run.id}>
                    <label
                      className={`flex min-h-[44px] cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors duration-200 ${
                        checked
                          ? "border-charcoal bg-platinum/40"
                          : "border-line bg-paper hover:border-charcoal"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleRun(run.id)}
                        className="h-5 w-5 shrink-0 accent-[#16161a]"
                      />
                      <span className="text-sm font-medium text-charcoal">
                        {subjectLabel(run)}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </fieldset>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="compare-baselines" className={LABEL_STYLES}>
              Extra baseline names
            </label>
            <input
              id="compare-baselines"
              type="text"
              value={baselineNames}
              onChange={(e) => setBaselineNames(e.target.value)}
              placeholder="deterministic_rule, keyword_heuristic"
              className={INPUT_STYLES}
            />
            <p className={HINT_STYLES}>Comma-separated; added as baselines.</p>
          </div>
          <div>
            <label htmlFor="compare-incumbent" className={LABEL_STYLES}>
              Incumbent intelligence version id
            </label>
            <input
              id="compare-incumbent"
              type="text"
              value={incumbentVersionId}
              onChange={(e) => setIncumbentVersionId(e.target.value)}
              placeholder="Optional"
              className={INPUT_STYLES}
            />
          </div>
        </div>

        <div className="mt-4">
          <button
            type="submit"
            disabled={!canCompare}
            className={BUTTON_PRIMARY}
          >
            {comparing ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <GitCompareArrows className="h-4 w-4" aria-hidden="true" />
            )}
            {comparing ? "Comparing…" : "Compare"}
          </button>
          {!comparing && selectedRunIds.length + extraSubjects.length < 2 && (
            <p className={HINT_STYLES}>Select at least two subjects.</p>
          )}
        </div>
      </form>

      {report && (
        <div className="mt-6 border-t border-line pt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-display text-base font-bold text-charcoal">
              Comparison report
            </h3>
            <p className="text-xs text-muted-ink">
              Generated{" "}
              {Number.isNaN(new Date(report.generated_at).getTime())
                ? report.generated_at
                : new Date(report.generated_at).toLocaleString("en-US")}
            </p>
          </div>

          {report.baseline_bar && (
            <p className="mt-2 text-sm text-muted-ink">
              Baseline bar:{" "}
              <span className="font-semibold text-charcoal">
                {(report.baseline_bar.accuracy * 100).toFixed(1)}% accuracy
              </span>
              {" · "}
              {report.baseline_bar.latency_ms_p50} ms p50
              {" · $"}
              {report.baseline_bar.cost_usd_per_1k}/1k
            </p>
          )}

          <div className="mt-4 overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-platinum/40">
                  <th
                    scope="col"
                    className="px-4 py-3 text-xs font-semibold tracking-wide text-muted-ink uppercase"
                  >
                    Metric
                  </th>
                  {report.results.map((result, i) => (
                    <th
                      key={resultKey(result)}
                      scope="col"
                      className={`px-4 py-3 text-xs font-semibold tracking-wide uppercase ${
                        i === winnerIdx ? "text-charcoal" : "text-muted-ink"
                      }`}
                    >
                      <span
                        className={
                          i === winnerIdx
                            ? "rounded bg-charcoal px-2 py-1 text-platinum"
                            : ""
                        }
                      >
                        {result.subject.kind} · {result.subject.ref ?? "—"}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {QUALITY_ROWS.map((row) => (
                  <tr
                    key={row.key}
                    className="border-b border-line last:border-0"
                  >
                    <th
                      scope="row"
                      className="px-4 py-2.5 text-xs font-semibold text-muted-ink"
                    >
                      {row.label}
                    </th>
                    {report.results.map((result, i) => (
                      <td
                        key={resultKey(result)}
                        className={`px-4 py-2.5 font-mono text-[13px] ${
                          i === winnerIdx
                            ? "font-bold text-charcoal"
                            : "text-ink"
                        }`}
                      >
                        {formatQv(result.quality_vector?.[row.key] ?? null)}
                      </td>
                    ))}
                  </tr>
                ))}
                <tr className="border-b border-line last:border-0">
                  <th
                    scope="row"
                    className="px-4 py-2.5 text-xs font-semibold text-muted-ink"
                  >
                    Beats bar
                  </th>
                  {report.results.map((result, _i) => (
                    <td key={resultKey(result, "bar-")} className="px-4 py-2.5">
                      {result.beats_bar === null ? (
                        <span className="text-muted-ink">—</span>
                      ) : result.beats_bar ? (
                        <StatusPill status="COMPLETED" />
                      ) : (
                        <StatusPill status="FAILED" />
                      )}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th
                    scope="row"
                    className="px-4 py-2.5 text-xs font-semibold text-muted-ink"
                  >
                    Beats incumbent
                  </th>
                  {report.results.map((result, _i) => (
                    <td key={resultKey(result, "inc-")} className="px-4 py-2.5">
                      {result.beats_incumbent === null ? (
                        <span className="text-muted-ink">—</span>
                      ) : result.beats_incumbent ? (
                        <StatusPill status="APPROVED" />
                      ) : (
                        <StatusPill status="FAILED" />
                      )}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted-ink">
            Beats-bar cells use the report status tones (dark = yes, red = no).
          </p>

          {report.winner && (
            <p className="mt-4 text-sm text-charcoal">
              Winner:{" "}
              <span className="font-bold">
                {report.results[winnerIdx]?.subject.ref ?? report.winner}
              </span>
            </p>
          )}

          {report.notes.length > 0 && (
            <div className="mt-4">
              <h4 className="text-sm font-bold text-charcoal">Notes</h4>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-ink">
                {report.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
