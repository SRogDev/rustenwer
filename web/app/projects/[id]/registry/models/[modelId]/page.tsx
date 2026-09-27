import { ArrowLeft, Lock } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Model, ModelVersion } from "../../../../../../../shared/types";
import { ModelVersionDiff } from "../../../../../../components/ModelVersionDiff";
import { OfflineBanner } from "../../../../../../components/OfflineBanner";
import { StatusPill } from "../../../../../../components/StatusPill";
import type { ModelLineage } from "../../../../../../lib/api";
import {
  ApiError,
  getModelLineage,
  isApiOfflineError,
  listModels,
  listModelVersions,
  MOCK_MODEL_VERSIONS,
  MOCK_MODELS,
} from "../../../../../../lib/api";

export const metadata: Metadata = {
  title: "Model detail",
  description: "Rustenwer model version chain and lineage.",
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

const LINEAGE_FIELDS: {
  key:
    | "dataset_version_id"
    | "training_strategy"
    | "code_version"
    | "template_version"
    | "seed"
    | "base_model";
  label: string;
}[] = [
  { key: "dataset_version_id", label: "Dataset version" },
  { key: "training_strategy", label: "Training strategy" },
  { key: "code_version", label: "Code version" },
  { key: "template_version", label: "Template version" },
  { key: "seed", label: "Seed" },
  { key: "base_model", label: "Base model" },
];

export default async function ModelDetailPage({
  params,
}: {
  params: Promise<{ id: string; modelId: string }>;
}) {
  const { id, modelId } = await params;

  const modelsResult = await withOffline(() => listModels(id), MOCK_MODELS);
  const model: Model | null =
    modelsResult.data.find((m) => m.id === modelId) ?? null;
  if (!model) notFound();

  const versionsResult = await withOffline(
    () => listModelVersions(modelId),
    MOCK_MODEL_VERSIONS.filter((v) => v.model_id === modelId),
  );
  const versions: ModelVersion[] = [...versionsResult.data].sort(
    (a, b) => b.version - a.version,
  );

  // The Phase 3 lineage endpoint is optional enrichment: the version records
  // themselves already carry the lineage fields. A 404/501 simply means the
  // backend has not implemented it yet; the client-side diff below still works.
  let lineage: ModelLineage | null = null;
  if (!versionsResult.offline) {
    try {
      lineage = await getModelLineage(modelId);
    } catch (err) {
      if (!(err instanceof ApiError)) throw err;
      lineage = null;
    }
  }

  const offline = modelsResult.offline || versionsResult.offline;
  const backHref = `/projects/${id}/registry`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={backHref}
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
          {model.name}
        </h1>
        <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
          {model.description ?? "No description yet."}
        </p>
        <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-muted-ink">Model ID</dt>
            <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
              {model.id}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Versions</dt>
            <dd className="mt-1 text-charcoal">{versions.length}</dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Registered</dt>
            <dd className="mt-1 text-charcoal">
              {formatDateTime(model.created_at)}
            </dd>
          </div>
        </dl>
      </div>

      <section aria-labelledby="chain-heading" className="mt-10">
        <h2
          id="chain-heading"
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          Version chain
        </h2>
        {versions.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-line bg-card p-8 text-center">
            <p className="text-sm text-muted-ink">
              No versions registered for this model yet.
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
                  <div className="flex items-center gap-2">
                    {version.lineage_locked && (
                      <span className="inline-flex min-h-[28px] items-center gap-1 rounded-full bg-platinum-deep px-3 py-1 text-xs font-semibold tracking-wide text-charcoal uppercase">
                        <Lock className="h-3 w-3" aria-hidden="true" />
                        Lineage locked
                      </span>
                    )}
                    <StatusPill
                      status={version.created_at ? "ACTIVE" : "DRAFT"}
                    />
                  </div>
                </div>

                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                  {LINEAGE_FIELDS.map(({ key, label }) => (
                    <div
                      key={key}
                      className="rounded-lg bg-platinum/30 px-3 py-2"
                    >
                      <dt className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                        {label}
                      </dt>
                      <dd className="mt-0.5 max-w-full font-mono text-[13px] break-words text-charcoal">
                        {formatScalar(version[key])}
                      </dd>
                    </div>
                  ))}
                </dl>

                <dl className="mt-3 grid gap-4 border-t border-line pt-3 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="font-semibold text-muted-ink">Metrics</dt>
                    <dd className="mt-1 font-mono text-[13px] break-words text-charcoal">
                      {formatScalar(version.metrics)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted-ink">Artifact</dt>
                    <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
                      {version.artifact_uri ?? "—"}
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

      <section aria-labelledby="diff-heading" className="mt-10">
        <h2
          id="diff-heading"
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          What changed between versions
        </h2>
        <div className="mt-4 rounded-xl border border-line bg-card p-5 sm:p-6">
          <ModelVersionDiff versions={versions} />
        </div>
        {lineage && lineage.changes.length > 0 && (
          <div className="mt-4 rounded-xl border border-line bg-card p-5 sm:p-6">
            <h3 className="font-display text-base font-bold text-charcoal">
              Backend-reported changes
            </h3>
            <ul className="mt-3 space-y-3">
              {lineage.changes.map((change) => (
                <li key={`${change.from_version}-${change.to_version}`}>
                  <p className="text-sm font-semibold text-charcoal">
                    v{change.from_version} → v{change.to_version}
                  </p>
                  {change.changed_fields.length > 0 ? (
                    <p className="mt-1 font-mono text-[13px] break-all text-muted-ink">
                      {change.changed_fields.join(", ")}
                    </p>
                  ) : (
                    <p className="mt-1 text-sm text-muted-ink">
                      No lineage differences — metadata-only change.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
