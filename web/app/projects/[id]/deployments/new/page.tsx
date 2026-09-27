import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Intelligence,
  IntelligenceSpec,
  IntelligenceVersion,
} from "../../../../../../shared/types";
import { DeployIntelligenceForm } from "../../../../../components/DeployIntelligenceForm";
import { OfflineBanner } from "../../../../../components/OfflineBanner";
import {
  isApiOfflineError,
  listIntelligences,
  listIntelligenceVersions,
  listSpecs,
  MOCK_INTELLIGENCE_VERSIONS,
  MOCK_INTELLIGENCES,
  MOCK_SPECS,
} from "../../../../../lib/api";

export const metadata: Metadata = {
  title: "Deploy an intelligence",
  description: "Deploy an immutable intelligence version to production.",
};

/** Always render on demand: registry data must be fresh. */
export const dynamic = "force-dynamic";

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

export default async function NewDeploymentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ intelligence?: string; version?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;

  const [intelligencesResult, specsResult] = await Promise.all([
    withOffline(() => listIntelligences(id), MOCK_INTELLIGENCES),
    withOffline(() => listSpecs(id), MOCK_SPECS),
  ]);
  const intelligences: Intelligence[] = intelligencesResult.data;
  const specs: IntelligenceSpec[] = specsResult.data;

  const versionsByIntelligence: Record<string, IntelligenceVersion[]> = {};
  for (const intel of intelligences) {
    const result = await withOffline(
      () => listIntelligenceVersions(intel.id),
      MOCK_INTELLIGENCE_VERSIONS.filter((v) => v.intelligence_id === intel.id),
    );
    versionsByIntelligence[intel.id] = [...result.data].sort(
      (a, b) => b.version - a.version,
    );
  }

  if (intelligences.length === 0) notFound();
  const offline = intelligencesResult.offline || specsResult.offline;

  // Preselect the version passed as ?version=<version_id> (e.g. from an
  // intelligence detail page's "Deploy this version" link).
  let preselectedVersionId: string | undefined;
  if (query.version) {
    const owns = Object.values(versionsByIntelligence).some((versions) =>
      versions.some((v) => v.id === query.version),
    );
    if (owns) preselectedVersionId = query.version;
  } else if (query.intelligence) {
    preselectedVersionId = versionsByIntelligence[query.intelligence]?.[0]?.id;
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
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
          Deploy an intelligence
        </h1>
        <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
          Deployments serve an immutable intelligence version — never a bare
          model. Publishing a new version never changes a live deployment.
        </p>
        <div className="mt-6 border-t border-line pt-6">
          <DeployIntelligenceForm
            projectId={id}
            intelligences={intelligences}
            versionsByIntelligence={versionsByIntelligence}
            specs={specs}
            preselectedVersionId={preselectedVersionId}
          />
        </div>
      </div>
    </div>
  );
}
