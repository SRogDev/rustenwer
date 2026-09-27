import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Benchmark,
  Intelligence,
  Model,
  Project,
} from "../../../../../shared/types";
import { OfflineBanner } from "../../../../components/OfflineBanner";
import { RegistryTabs } from "../../../../components/RegistryTabs";
import {
  getProject,
  isApiOfflineError,
  listBenchmarks,
  listIntelligences,
  listModels,
  MOCK_BENCHMARKS,
  MOCK_INTELLIGENCES,
  MOCK_MODELS,
  MOCK_PROJECTS,
} from "../../../../lib/api";

export const metadata: Metadata = {
  title: "Registry",
  description: "Rustenwer model and intelligence registry with benchmarks.",
};

/** Always render on demand: registry data must be fresh. */
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

export default async function RegistryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const projectResult = await withOffline(() => getProject(id), null);
  const project: Project | null = projectResult.offline
    ? (MOCK_PROJECTS.find((p) => p.id === id) ?? null)
    : projectResult.data;
  if (!project) notFound();

  const [modelsResult, intelligencesResult, benchmarksResult] =
    await Promise.all([
      withOffline(() => listModels(id), MOCK_MODELS),
      withOffline(() => listIntelligences(id), MOCK_INTELLIGENCES),
      withOffline(() => listBenchmarks(id), MOCK_BENCHMARKS),
    ]);

  const offline =
    projectResult.offline ||
    modelsResult.offline ||
    intelligencesResult.offline ||
    benchmarksResult.offline;

  const models: Model[] = modelsResult.data;
  const intelligences: Intelligence[] = intelligencesResult.data;
  const benchmarks: Benchmark[] = benchmarksResult.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/projects/${id}`}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {project.name}
      </Link>

      {offline && (
        <div className="mt-4">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-4">
        <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
          Registry
        </h1>
        <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
          Immutable model versions with lineage, packaged intelligences, and the
          benchmarks they are evaluated against.
        </p>
      </div>

      <div className="mt-8">
        <RegistryTabs
          projectId={id}
          models={models}
          intelligences={intelligences}
          benchmarks={benchmarks}
        />
      </div>
    </div>
  );
}
