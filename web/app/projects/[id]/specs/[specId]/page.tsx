import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Dataset,
  Evaluation,
  IntelligenceSpec,
} from "../../../../../../shared/types";
import { OfflineBanner } from "../../../../../components/OfflineBanner";
import { SpecActions } from "../../../../../components/SpecActions";
import { StatusPill } from "../../../../../components/StatusPill";
import {
  getSpec,
  isApiOfflineError,
  listDatasets,
  listEvaluations,
  MOCK_DATASETS,
  MOCK_EVALUATIONS,
  MOCK_SPECS,
} from "../../../../../lib/api";

export const metadata: Metadata = {
  title: "Spec detail",
  description: "Rustenwer Intelligence Spec detail.",
};

/** Always render on demand: spec data + offline detection must be fresh. */
export const dynamic = "force-dynamic";

function JsonBlock({ value }: { value: Record<string, unknown> }) {
  return (
    <pre className="overflow-x-auto rounded-lg bg-paper p-3 font-mono text-xs leading-5 text-charcoal">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
        {label}
      </dt>
      <dd className="mt-1.5 text-sm leading-6 text-charcoal">{children}</dd>
    </div>
  );
}

export default async function SpecDetailPage({
  params,
}: {
  params: Promise<{ id: string; specId: string }>;
}) {
  const { id, specId } = await params;

  let spec: IntelligenceSpec | null = null;
  let datasets: Dataset[] = [];
  let evaluations: Evaluation[] = [];
  let offline = false;

  try {
    const [fetchedSpec, fetchedDatasets, fetchedEvaluations] =
      await Promise.all([
        getSpec(specId),
        listDatasets(id),
        listEvaluations(id),
      ]);
    spec = fetchedSpec;
    datasets = fetchedDatasets;
    evaluations = fetchedEvaluations.filter((e) => e.spec_id === specId);
  } catch (err) {
    if (isApiOfflineError(err)) {
      offline = true;
      spec = MOCK_SPECS.find((s) => s.id === specId) ?? null;
      datasets = MOCK_DATASETS;
      evaluations = MOCK_EVALUATIONS.filter((e) => e.spec_id === specId);
    } else {
      throw err;
    }
  }

  if (!spec) notFound();

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/projects/${id}`}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to project
      </Link>

      {offline && (
        <div className="mt-4">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-4 rounded-xl border border-line bg-card p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              Intelligence Spec · v{spec.version}
            </p>
            <h1 className="mt-1 font-display text-3xl font-bold tracking-tight text-charcoal">
              {spec.name}
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
              {spec.description ?? "No description yet."}
            </p>
          </div>
          <StatusPill status={spec.status} />
        </div>

        <dl className="mt-6 grid gap-6 border-t border-line pt-6 sm:grid-cols-2">
          <Field label="Problem statement">
            <span className="whitespace-pre-wrap">
              {spec.problem_statement}
            </span>
          </Field>
          <Field label="Type of intelligence">
            {spec.intelligence_primitive.replace(/_/g, " ")}
          </Field>
          <Field label="Input schema">
            <JsonBlock value={spec.input_schema} />
          </Field>
          <Field label="Output schema">
            <JsonBlock value={spec.output_schema} />
          </Field>
          {spec.latency_requirements && (
            <Field label="Latency requirements">
              <JsonBlock value={spec.latency_requirements} />
            </Field>
          )}
          {spec.quality_requirements && (
            <Field label="Quality requirements">
              <JsonBlock value={spec.quality_requirements} />
            </Field>
          )}
          {spec.cost_requirements && (
            <Field label="Cost requirements">
              <JsonBlock value={spec.cost_requirements} />
            </Field>
          )}
          {spec.memory_requirements && (
            <Field label="Memory requirements">
              <JsonBlock value={spec.memory_requirements} />
            </Field>
          )}
          {spec.reliability_requirements && (
            <Field label="Reliability requirements">
              <JsonBlock value={spec.reliability_requirements} />
            </Field>
          )}
          {spec.deployment_requirements && (
            <Field label="Deployment requirements">
              <JsonBlock value={spec.deployment_requirements} />
            </Field>
          )}
          {spec.constraints.length > 0 && (
            <Field label="Constraints">
              <ul className="list-disc space-y-1 pl-5">
                {spec.constraints.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </Field>
          )}
          {spec.available_data && (
            <Field label="Available data">{spec.available_data}</Field>
          )}
          {spec.evaluation_definition && (
            <Field label="Evaluation definition">
              {spec.evaluation_definition}
            </Field>
          )}
          {spec.human_review_policy && (
            <Field label="Human review policy">
              {spec.human_review_policy}
            </Field>
          )}
        </dl>
      </div>

      <SpecActions
        projectId={id}
        specId={specId}
        initialStatus={spec.status}
        datasets={datasets}
        initialEvaluations={evaluations}
      />
    </div>
  );
}
