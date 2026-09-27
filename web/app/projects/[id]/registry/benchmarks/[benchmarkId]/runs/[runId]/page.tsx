import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Benchmark,
  EvaluationRun,
} from "../../../../../../../../../shared/types";
import { EvaluationRunDetail } from "../../../../../../../../components/EvaluationRunDetail";
import { OfflineBanner } from "../../../../../../../../components/OfflineBanner";
import {
  getBenchmark,
  getEvaluationRun,
  isApiOfflineError,
  MOCK_BENCHMARKS,
  MOCK_EVAL_RUNS,
} from "../../../../../../../../lib/api";

export const metadata: Metadata = {
  title: "Evaluation run",
  description: "Rustenwer evaluation run detail with quality vector.",
};

/** Always render on demand: run state must be fresh. */
export const dynamic = "force-dynamic";

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

export default async function EvaluationRunPage({
  params,
}: {
  params: Promise<{ id: string; benchmarkId: string; runId: string }>;
}) {
  const { id, benchmarkId, runId } = await params;

  const benchmarkResult = await withOffline(
    () => getBenchmark(benchmarkId),
    MOCK_BENCHMARKS.find((b) => b.id === benchmarkId) ?? null,
  );
  const benchmark: Benchmark | null = benchmarkResult.data;

  const runResult = await withOffline(
    () => getEvaluationRun(runId),
    MOCK_EVAL_RUNS.find((r) => r.id === runId) ?? null,
  );
  const run: EvaluationRun | null = runResult.data;
  if (!run) notFound();

  const offline = benchmarkResult.offline || runResult.offline;
  const backHref = `/projects/${id}/registry/benchmarks/${benchmarkId}`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={backHref}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {benchmark?.name ?? "Benchmark"}
      </Link>

      {offline && (
        <div className="mt-4">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-4">
        <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
          {run.name}
        </h1>
        <p className="mt-2 font-mono text-[13px] text-muted-ink">{run.id}</p>
      </div>

      <div className="mt-6">
        <EvaluationRunDetail initial={run} backHref={backHref} />
      </div>
    </div>
  );
}
