import { ArrowLeft, Terminal } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Deployment,
  IntelligenceVersion,
} from "../../../../../../shared/types";
import { ArchitectureDiagram } from "../../../../../components/ArchitectureDiagram";
import { DeploymentStatusButtons } from "../../../../../components/DeploymentStatusButtons";
import { InferConsole } from "../../../../../components/InferConsole";
import { OfflineBanner } from "../../../../../components/OfflineBanner";
import { StatusPill } from "../../../../../components/StatusPill";
import {
  API_BASE_URL,
  getDeployment,
  getIntelligenceVersionById,
  isApiOfflineError,
} from "../../../../../lib/api";

export const metadata: Metadata = {
  title: "Deployment detail",
  description:
    "Rustenwer deployment: pinned intelligence version and endpoint.",
};

/** Always render on demand: deployment state must be fresh. */
export const dynamic = "force-dynamic";

export default async function DeploymentDetailPage({
  params,
}: {
  params: Promise<{ id: string; deploymentId: string }>;
}) {
  const { id, deploymentId } = await params;

  let deployment: Deployment;
  const offline = false;
  try {
    deployment = await getDeployment(deploymentId);
  } catch (err) {
    if (isApiOfflineError(err)) {
      return (
        <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 sm:py-14">
          <OfflineBanner />
          <p className="mt-4 text-sm text-muted-ink">
            The API is offline, so deployment details are unavailable.
          </p>
        </div>
      );
    }
    notFound();
  }
  if (deployment.project_id !== id) notFound();

  let version: IntelligenceVersion | null = null;
  if (deployment.intelligence_version_id) {
    try {
      version = await getIntelligenceVersionById(
        deployment.intelligence_version_id,
      );
    } catch {
      version = null;
    }
  }

  const endpointPath = `/api/v1/deployments/${deploymentId}/infer`;
  const curl = [
    "curl -X POST \\",
    `  ${API_BASE_URL}${endpointPath} \\`,
    '  -H "Content-Type: application/json" \\',
    '  -H "Authorization: Bearer $RUSTENWER_TOKEN" \\',
    `  -d '{"inputs": {}}'`,
  ].join("\n");

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
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
              {deployment.name}
            </h1>
            <p className="mt-2 font-mono text-[13px] break-all text-muted-ink">
              {deploymentId}
            </p>
          </div>
          <StatusPill status={deployment.status} />
        </div>

        <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-muted-ink">Provider</dt>
            <dd className="mt-1 font-mono text-[13px] text-charcoal">
              {deployment.provider}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">
              Pinned intelligence version
            </dt>
            <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
              {deployment.intelligence_version_id ?? "—"}
              {version && (
                <span className="ml-2 text-muted-ink">v{version.version}</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Spec</dt>
            <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
              {deployment.spec_id}
            </dd>
          </div>
        </dl>

        <div className="mt-6 border-t border-line pt-6">
          <h2 className="text-sm font-semibold text-charcoal">
            Lifecycle state
          </h2>
          <div className="mt-3">
            <DeploymentStatusButtons
              deploymentId={deploymentId}
              status={deployment.status}
            />
          </div>
          <p className="mt-2 text-sm text-muted-ink">
            Only <span className="font-semibold">ACTIVE</span> deployments serve
            inference.
          </p>
        </div>
      </div>

      <section
        aria-labelledby="endpoint-heading"
        className="mt-8 rounded-xl border border-line bg-card p-6 sm:p-8"
      >
        <h2
          id="endpoint-heading"
          className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          <Terminal className="h-5 w-5" aria-hidden="true" />
          Endpoint
        </h2>
        <p className="mt-2 font-mono text-sm break-all text-charcoal">
          POST {endpointPath}
        </p>
        <pre className="mt-4 overflow-x-auto rounded-lg bg-charcoal px-4 py-3 font-mono text-[13px] leading-6 text-platinum">
          {curl}
        </pre>
      </section>

      <section
        aria-labelledby="console-heading"
        className="mt-8 rounded-xl border border-line bg-card p-6 sm:p-8"
      >
        <h2
          id="console-heading"
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          Try it
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted-ink">
          Run a live inference against this deployment. The output is the
          machine-readable result of the pinned immutable version.
        </p>
        <div className="mt-4">
          <InferConsole
            deploymentId={deploymentId}
            inputSchema={version?.input_schema ?? null}
          />
        </div>
      </section>

      {version?.architecture && (
        <section
          aria-labelledby="arch-heading"
          className="mt-8 rounded-xl border border-line bg-card p-6 sm:p-8"
        >
          <h2
            id="arch-heading"
            className="font-display text-2xl font-bold tracking-tight text-charcoal"
          >
            Pinned architecture
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-ink">
            The exact component snapshot this deployment executes — immutable
            since v{version.version} was published.
          </p>
          <div className="mt-4">
            <ArchitectureDiagram architecture={version.architecture} />
          </div>
        </section>
      )}
    </div>
  );
}
