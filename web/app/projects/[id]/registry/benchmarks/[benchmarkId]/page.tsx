import { ArrowLeft, ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Benchmark,
  EvaluationRun,
  ModelVersion,
} from "../../../../../../../shared/types";
import { ComparePanel } from "../../../../../../components/ComparePanel";
import { OfflineBanner } from "../../../../../../components/OfflineBanner";
import { RunEvaluationForm } from "../../../../../../components/RunEvaluationForm";
import { StatusPill } from "../../../../../../components/StatusPill";
import {
  getBenchmark,
  isApiOfflineError,
  listEvaluationRuns,
  listModels,
  listModelVersions,
  MOCK_BENCHMARKS,
  MOCK_EVAL_RUNS,
  MOCK_MODEL_VERSIONS,
  MOCK_MODELS,
} from "../../../../../../lib/api";

export const metadata: Metadata = {
  title: "Benchmark detail",
  description: "Rustenwer benchmark with evaluation runs and comparison.",
};

/** Always render on demand: run data must be fresh. */
export const dynamic = "force-dynamic";

function formatDateTime(iso: string): string {
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

/**
 * Fetch with per-resource offline fallback: reads serve the labeled mock
 * dataset when the API is unreachable; any other error propagates.
 */
async function withOffline<T>(
  fetch: () => Promise<T>,
  mock: T,
): Promise<{ data: T; offline: boolean }> {
  try {
    return { data: await fetch(), offline: false };
  } catch (err) {
    if (isApiOfflineError(err)) return { data: mock, offline: true };
    throw err;
  }
}

export default async function BenchmarkDetailPage({
  params,
}: {
  params: Promise<{ id: string; benchmarkId: string }>;
}) {
  const { id, benchmarkId } = await params;

  const benchmarkResult = await withOffline(
    () => getBenchmark(benchmarkId),
    MOCK_BENCHMARKS.find((b) => b.id === benchmarkId) ?? null,
  );
  const benchmark: Benchmark | null = benchmarkResult.data;
  if (!benchmark) notFound();

  const runsResult = await withOffline(
    () => listEvaluationRuns(id),
    MOCK_EVAL_RUNS.filter((r) => r.benchmark_id === benchmarkId),
  );
  const runs: EvaluationRun[] = runsResult.data
    .filter((r) => r.benchmark_id === benchmarkId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  // Model versions available as evaluation subjects (best effort; an empty
  // list simply hides the model_version option).
  const modelsResult = await withOffline(() => listModels(id), MOCK_MODELS);
  let modelVersions: ModelVersion[] = [];
  if (modelsResult.offline) {
    modelVersions = MOCK_MODEL_VERSIONS;
  } else {
    const settled = await Promise.allSettled(
      modelsResult.data.map((model) => listModelVersions(model.id)),
    );
    modelVersions = settled.flatMap((s) =>
      s.status === "fulfilled" ? s.value : [],
    );
  }
  const modelVersionOptions = modelVersions.map((v) => ({
    id: v.id,
    label: `v${v.version} · ${v.id.slice(0, 8)}`,
  }));

  const offline =
    benchmarkResult.offline || runsResult.offline || modelsResult.offline;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/projects/${id}/registry`}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Registry
      </Link>

      {offline && (
        <div className="mt-4">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-4 rounded-xl border border-line bg-card p-6 sm:p-8">
        <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
          {benchmark.name}
        </h1>
        <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
          {benchmark.description}
        </p>
        <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="font-semibold text-muted-ink">Metrics</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {benchmark.metrics.length === 0 ? (
                <span className="text-charcoal">—</span>
              ) : (
                benchmark.metrics.map((metric) => (
                  <StatusPill key={metric} status={metric} />
                ))
              )}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">
              Evaluation function
            </dt>
            <dd className="mt-1 font-mono text-[13px] break-words text-charcoal">
              {benchmark.evaluation_function}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Dataset version</dt>
            <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
              {benchmark.dataset_version_id ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Cost rules</dt>
            <dd className="mt-1 font-mono text-[13px] break-words text-charcoal">
              {formatScalar(benchmark.cost_rules)}
            </dd>
          </div>
        </dl>
      </div>

      <div className="mt-8">
        <RunEvaluationForm
          benchmarkId={benchmarkId}
          projectId={id}
          modelVersions={modelVersionOptions}
        />
      </div>

      <div className="mt-8">
        <ComparePanel benchmarkId={benchmarkId} runs={runs} />
      </div>

      <section aria-labelledby="runs-heading" className="mt-10">
        <h2
          id="runs-heading"
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          Evaluation runs
        </h2>
        {runs.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-line bg-card p-8 text-center">
            <p className="text-sm text-muted-ink">
              No runs on this benchmark yet. Start one above.
            </p>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-card">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-platinum/40 text-xs tracking-wide text-muted-ink uppercase">
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Run
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Subject
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Task quality
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.id}
                    className="border-b border-line transition-colors duration-200 last:border-0 hover:bg-platinum/30"
                  >
                    <td className="px-4 py-3 font-semibold text-charcoal">
                      <Link
                        href={`/projects/${id}/registry/benchmarks/${benchmarkId}/runs/${run.id}`}
                        aria-label={`View evaluation run ${run.name}`}
                        className="rounded underline decoration-platinum-deep underline-offset-4 transition-colors duration-200 hover:decoration-charcoal"
                      >
                        {run.name}
                        <ArrowRight
                          className="ml-1 inline h-3.5 w-3.5"
                          aria-hidden="true"
                        />
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono text-[13px] text-muted-ink">
                      {run.subject.kind} · {run.subject.ref ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill status={run.status} />
                    </td>
                    <td className="px-4 py-3 text-charcoal">
                      {run.quality_vector?.task_quality === null ||
                      run.quality_vector?.task_quality === undefined
                        ? "—"
                        : `${(run.quality_vector.task_quality * 100).toFixed(1)}%`}
                    </td>
                    <td className="px-4 py-3 text-muted-ink">
                      {formatDateTime(run.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
