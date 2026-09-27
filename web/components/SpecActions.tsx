"use client";

import {
  BadgeCheck,
  BrainCircuit,
  FlaskConical,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type {
  Dataset,
  DatasetVersion,
  DiagnosisResult,
  Evaluation,
  IntelligenceSpecStatus,
} from "../../shared/types";
import {
  approveSpec,
  diagnoseSpec,
  isApiOfflineError,
  listDatasetVersions,
  runEvaluation,
} from "../lib/api";
import { StatusPill } from "./StatusPill";

function formatPercent(value: number | null): string {
  return value === null ? "n/a" : `${(value * 100).toFixed(1)}%`;
}

/** The "No ML needed" callout (Rule 13) — first-class, not an edge case. */
function NoMlCallout({ diagnosis }: { diagnosis: DiagnosisResult }) {
  return (
    <div
      role="status"
      className="rounded-xl border-2 border-charcoal bg-platinum p-5"
    >
      <p className="flex items-center gap-2 font-display text-lg font-bold text-charcoal">
        <Sparkles className="h-5 w-5" aria-hidden="true" />
        No ML needed
      </p>
      <p className="mt-2 text-sm leading-6 text-ink">
        The Diagnostic Agent concluded this problem does not require a trained
        model. A deterministic solution — a rule, a lookup, a heuristic — is
        cheaper, faster, and easier to maintain.
      </p>
      {diagnosis.candidate_approaches.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Recommended approaches
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-charcoal">
            {diagnosis.candidate_approaches.map((approach) => (
              <li key={approach}>{approach}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DiagnosisCard({ diagnosis }: { diagnosis: DiagnosisResult }) {
  return (
    <div className="mt-4 rounded-xl border border-line bg-card p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-display text-lg font-bold text-charcoal">
          Diagnosis
        </h3>
        <span className="text-xs text-muted-ink">
          {new Date(diagnosis.diagnosed_at).toLocaleString("en-US", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>

      {!diagnosis.ml_necessary ? (
        <div className="mt-4">
          <NoMlCallout diagnosis={diagnosis} />
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <p className="text-sm leading-6 text-muted-ink">
            ML looks justified for this problem. The cheapest baselines still
            run first — any trained candidate must beat their bar.
          </p>
          <div>
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              Candidate approaches
            </p>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-charcoal">
              {diagnosis.candidate_approaches.map((approach) => (
                <li key={approach}>{approach}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="mt-4 border-t border-line pt-4">
        <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
          Rationale — the 10 diagnostic questions, condensed
        </p>
        <p className="mt-1.5 text-sm leading-6 whitespace-pre-wrap text-charcoal">
          {diagnosis.rationale}
        </p>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Data required
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-charcoal">
            {diagnosis.data_requirements.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Success metrics
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-charcoal">
            {diagnosis.success_metrics.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Key constraints
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-charcoal">
            {diagnosis.key_constraints.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function BaselineTable({ evaluation }: { evaluation: Evaluation }) {
  const results = evaluation.results;
  if (!results) return null;
  return (
    <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-card">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-line bg-platinum/40 text-xs tracking-wide text-muted-ink uppercase">
            <th scope="col" className="px-4 py-3 font-semibold">
              Baseline
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Accuracy
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              p50 latency
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Cost / 1k
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Bar to beat
            </th>
          </tr>
        </thead>
        <tbody>
          {results.baselines.map((baseline) => {
            const isBar =
              evaluation.results?.bar_to_beat.accuracy === baseline.accuracy &&
              baseline.accuracy !== null;
            return (
              <tr
                key={baseline.name}
                className="border-b border-line transition-colors duration-200 last:border-0 hover:bg-platinum/30"
              >
                <td className="px-4 py-3">
                  <span className="font-semibold text-charcoal">
                    {baseline.name}
                  </span>
                  <span className="mt-0.5 block max-w-xs text-xs text-muted-ink">
                    {baseline.description}
                  </span>
                </td>
                <td className="px-4 py-3 font-semibold text-charcoal">
                  {formatPercent(baseline.accuracy)}
                </td>
                <td className="px-4 py-3 text-charcoal">
                  {baseline.latency_ms_p50.toFixed(3)} ms
                </td>
                <td className="px-4 py-3 text-charcoal">
                  ${baseline.cost_usd_per_1k.toFixed(4)}
                </td>
                <td className="px-4 py-3">
                  {isBar ? (
                    <StatusPill status="COMPLETED" />
                  ) : (
                    <span className="text-xs text-muted-ink">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="border-t border-line bg-platinum/30 px-4 py-3 text-sm leading-6 text-ink">
        <span className="font-semibold">Recommendation: </span>
        {results.recommendation}
      </p>
    </div>
  );
}

export function SpecActions({
  projectId,
  specId,
  initialStatus,
  datasets,
  initialEvaluations,
}: {
  projectId: string;
  specId: string;
  initialStatus: IntelligenceSpecStatus;
  datasets: Dataset[];
  initialEvaluations: Evaluation[];
}) {
  const router = useRouter();
  const [status, setStatus] = useState<IntelligenceSpecStatus>(initialStatus);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [evaluations, setEvaluations] =
    useState<Evaluation[]>(initialEvaluations);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"diagnose" | "approve" | "evaluate" | null>(
    null,
  );

  // Baseline evaluation form state
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? "");
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [versionId, setVersionId] = useState("");
  const [versionsLoading, setVersionsLoading] = useState(false);

  const canApprove = status === "DRAFT" || status === "DIAGNOSED";

  function offlineMessage(verb: string): string {
    return `The API is offline, so the spec could not be ${verb}. Start the backend at http://localhost:8000 and try again.`;
  }

  async function handleDiagnose() {
    setBusy("diagnose");
    setError(null);
    try {
      const result = await diagnoseSpec(specId);
      setDiagnosis(result);
      setStatus("DIAGNOSED");
      router.refresh();
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? offlineMessage("diagnosed")
          : err instanceof Error
            ? err.message
            : "Diagnosis failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleApprove() {
    setBusy("approve");
    setError(null);
    try {
      const spec = await approveSpec(specId);
      setStatus(spec.status);
      router.refresh();
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? offlineMessage("approved")
          : err instanceof Error
            ? err.message
            : "Approval failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleDatasetChange(next: string) {
    setDatasetId(next);
    setVersionId("");
    if (!next) {
      setVersions([]);
      return;
    }
    setVersionsLoading(true);
    try {
      const list = await listDatasetVersions(next);
      setVersions(list);
      const first = list[0];
      if (first) setVersionId(first.id);
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so dataset versions could not be loaded."
          : err instanceof Error
            ? err.message
            : "Failed to load dataset versions.",
      );
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  }

  async function handleEvaluate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!versionId) {
      setError("Pick a dataset version to evaluate against.");
      return;
    }
    setBusy("evaluate");
    setError(null);
    try {
      const evaluation = await runEvaluation(projectId, {
        spec_id: specId,
        dataset_version_id: versionId,
      });
      setEvaluations((prev) => [evaluation, ...prev]);
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? offlineMessage("evaluated")
          : err instanceof Error
            ? err.message
            : "Evaluation failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-6 space-y-6">
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={busy !== null}
          onClick={handleDiagnose}
          className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy === "diagnose" ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <BrainCircuit className="h-4 w-4" aria-hidden="true" />
          )}
          {busy === "diagnose" ? "Diagnosing…" : "Diagnose"}
        </button>
        <button
          type="button"
          disabled={busy !== null || !canApprove}
          onClick={handleApprove}
          title={
            canApprove
              ? "Approve this spec"
              : "Only DRAFT or DIAGNOSED specs can be approved"
          }
          className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg border border-line bg-paper px-5 py-2.5 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy === "approve" ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <BadgeCheck className="h-4 w-4" aria-hidden="true" />
          )}
          {busy === "approve" ? "Approving…" : "Approve"}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg bg-[#DC2626]/10 px-3.5 py-2.5 text-sm font-medium text-[#8f1d1d]"
        >
          {error}
        </p>
      )}

      {diagnosis && <DiagnosisCard diagnosis={diagnosis} />}

      <div className="rounded-xl border border-line bg-card p-5 sm:p-6">
        <h3 className="flex items-center gap-2 font-display text-lg font-bold text-charcoal">
          <FlaskConical className="h-5 w-5" aria-hidden="true" />
          Baseline evaluation
        </h3>
        <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-ink">
          Rule 9: cheap baselines run before any training is proposed. The best
          baseline sets the bar to beat.
        </p>
        <form
          onSubmit={handleEvaluate}
          className="mt-4 grid gap-4 sm:grid-cols-3"
        >
          <div>
            <label
              htmlFor="eval-dataset"
              className="mb-1.5 block text-sm font-semibold text-charcoal"
            >
              Dataset
            </label>
            <select
              id="eval-dataset"
              value={datasetId}
              onChange={(e) => handleDatasetChange(e.target.value)}
              className="block w-full min-h-[44px] cursor-pointer rounded-lg border border-line bg-paper px-3.5 text-base text-charcoal transition-colors duration-200 focus:border-charcoal"
            >
              <option value="">Select a dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="eval-version"
              className="mb-1.5 block text-sm font-semibold text-charcoal"
            >
              Version
            </label>
            <select
              id="eval-version"
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
              disabled={!datasetId || versionsLoading}
              className="block w-full min-h-[44px] cursor-pointer rounded-lg border border-line bg-paper px-3.5 text-base text-charcoal transition-colors duration-200 focus:border-charcoal disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">
                {versionsLoading ? "Loading…" : "Select a version…"}
              </option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version} — {v.stats.row_count} rows
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={busy !== null || !versionId}
              className="inline-flex min-h-[44px] w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
            >
              {busy === "evaluate" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <FlaskConical className="h-4 w-4" aria-hidden="true" />
              )}
              {busy === "evaluate" ? "Running…" : "Run baselines"}
            </button>
          </div>
        </form>

        {evaluations.length > 0 && (
          <div className="mt-6 space-y-6">
            {evaluations.map((evaluation) => (
              <div key={evaluation.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-charcoal">
                    {evaluation.name}
                  </p>
                  <StatusPill status={evaluation.status} />
                </div>
                <BaselineTable evaluation={evaluation} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
