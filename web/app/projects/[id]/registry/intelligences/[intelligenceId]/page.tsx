import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Intelligence,
  IntelligenceVersion,
} from "../../../../../../../shared/types";
import { OfflineBanner } from "../../../../../../components/OfflineBanner";
import { PromoteIntelligenceButton } from "../../../../../../components/PromoteIntelligenceButton";
import { StatusPill } from "../../../../../../components/StatusPill";
import {
  getIntelligence,
  isApiOfflineError,
  listIntelligences,
  listIntelligenceVersions,
  MOCK_INTELLIGENCE_VERSIONS,
  MOCK_INTELLIGENCES,
} from "../../../../../../lib/api";

export const metadata: Metadata = {
  title: "Intelligence detail",
  description: "Rustenwer intelligence version chain and components.",
};

/** Always render on demand: version data must be fresh. */
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

/**
 * Renders an intelligence version's resolved components. Known component
 * keys (models, baselines, harness) get a readable rendering; anything
 * else falls back to JSON so unknown component shapes stay visible.
 */
function ResolvedComponents({
  components,
}: {
  components: Record<string, unknown>;
}) {
  const entries = Object.entries(components);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-ink">No components recorded.</p>;
  }
  return (
    <dl className="space-y-3">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            {key.replace(/_/g, " ")}
          </dt>
          <dd className="mt-1.5">
            {key === "models" && Array.isArray(value) ? (
              <ul className="space-y-1.5">
                {value.map((item) => {
                  const label =
                    typeof item === "object" && item !== null
                      ? `${String((item as Record<string, unknown>).name ?? "model")} v${String((item as Record<string, unknown>).version ?? "?")}`
                      : formatScalar(item);
                  return (
                    <li
                      key={label}
                      className="inline-block rounded-lg bg-platinum/40 px-3 py-1.5 font-mono text-[13px] text-charcoal"
                    >
                      {label}
                    </li>
                  );
                })}
              </ul>
            ) : key === "baselines" && Array.isArray(value) ? (
              <div className="flex flex-wrap gap-1.5">
                {value.map((item) => (
                  <StatusPill
                    key={formatScalar(item)}
                    status={formatScalar(item)}
                  />
                ))}
              </div>
            ) : key === "harness" ? (
              <p className="font-mono text-[13px] text-charcoal">
                {formatScalar(value)}
              </p>
            ) : (
              <pre className="overflow-x-auto rounded-lg bg-platinum/30 px-3 py-2 font-mono text-[13px] break-words whitespace-pre-wrap text-charcoal">
                {formatScalar(value)}
              </pre>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default async function IntelligenceDetailPage({
  params,
}: {
  params: Promise<{ id: string; intelligenceId: string }>;
}) {
  const { id, intelligenceId } = await params;

  const intelligencesResult = await withOffline(
    () => listIntelligences(id),
    MOCK_INTELLIGENCES,
  );
  let intelligence: Intelligence | null =
    intelligencesResult.data.find((i) => i.id === intelligenceId) ?? null;
  if (!intelligence && !intelligencesResult.offline) {
    // The detail endpoint may know an id the list does not; try it directly.
    try {
      const direct = await getIntelligence(intelligenceId);
      if (direct.project_id !== id) notFound();
      intelligence = direct;
    } catch {
      notFound();
    }
  }
  if (!intelligence) notFound();

  const versionsResult = await withOffline(
    () => listIntelligenceVersions(intelligenceId),
    MOCK_INTELLIGENCE_VERSIONS.filter(
      (v) => v.intelligence_id === intelligenceId,
    ),
  );
  const versions: IntelligenceVersion[] = [...versionsResult.data].sort(
    (a, b) => b.version - a.version,
  );

  const offline = intelligencesResult.offline || versionsResult.offline;
  const name = intelligence?.name ?? "Intelligence";

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
          {name}
        </h1>
        <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
          {intelligence?.description ?? "No description yet."}
        </p>
        <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-muted-ink">Intelligence ID</dt>
            <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
              {intelligenceId}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Primitive</dt>
            <dd className="mt-1 text-charcoal">
              {intelligence?.primitive?.replace(/_/g, " ") ?? "none"}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Versions</dt>
            <dd className="mt-1 text-charcoal">{versions.length}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-8">
        <PromoteIntelligenceButton intelligenceId={intelligenceId} />
      </div>

      <section aria-labelledby="versions-heading" className="mt-10">
        <h2
          id="versions-heading"
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          Version chain
        </h2>
        {versions.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-line bg-card p-8 text-center">
            <p className="text-sm text-muted-ink">
              No versions yet. Versions are immutable packages of resolved
              components.
            </p>
          </div>
        ) : (
          <ol className="mt-4 space-y-4">
            {versions.map((version) => (
              <li
                key={version.id}
                className="rounded-xl border border-line bg-card p-5 sm:p-6"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-display text-lg font-bold text-charcoal">
                    v{version.version}
                  </h3>
                  <StatusPill status={version.status} />
                </div>
                {version.notes && (
                  <p className="mt-2 text-sm leading-6 text-muted-ink">
                    {version.notes}
                  </p>
                )}
                <div className="mt-4 border-t border-line pt-4">
                  <ResolvedComponents components={version.components} />
                </div>
                <dl className="mt-4 grid gap-4 border-t border-line pt-4 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="font-semibold text-muted-ink">
                      Best evaluation run
                    </dt>
                    <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
                      {version.best_evaluation_run_id ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted-ink">Created</dt>
                    <dd className="mt-1 text-charcoal">
                      {formatDateTime(version.created_at)}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
