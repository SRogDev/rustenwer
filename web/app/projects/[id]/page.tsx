import { ArrowLeft, ArrowRight, Database } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  Evaluation,
  IntelligenceSpec,
  Project,
  TrainingJob,
  UsageSummary,
} from "../../../../shared/types";
import { JobTransitionButtons } from "../../../components/JobTransitionButtons";
import { OfflineBanner } from "../../../components/OfflineBanner";
import { StatusBadge } from "../../../components/StatusBadge";
import { StatusPill } from "../../../components/StatusPill";
import { TerminationDemoButton } from "../../../components/TerminationDemoButton";
import {
  getProject,
  getUsageSummary,
  isApiOfflineError,
  listEvaluations,
  listSpecs,
  listTrainingJobs,
  MOCK_EVALUATIONS,
  MOCK_PROJECTS,
  MOCK_SPECS,
  MOCK_TRAINING_JOBS,
  MOCK_USAGE_SUMMARY,
} from "../../../lib/api";

export const metadata: Metadata = {
  title: "Project detail",
  description: "Rustenwer project detail.",
};

/** Always render on demand: project data + offline detection must be fresh. */
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

function formatPercent(value: number | null): string {
  return value === null ? "n/a" : `${(value * 100).toFixed(1)}%`;
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

function Section({
  id,
  title,
  children,
  action,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mt-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id={id}
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          {title}
        </h2>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-card p-8 text-center">
      <p className="text-sm text-muted-ink">{text}</p>
    </div>
  );
}

export default async function ProjectDetailPage({
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

  const [specsResult, jobsResult, evalsResult, usageResult] = await Promise.all(
    [
      withOffline(() => listSpecs(id), MOCK_SPECS),
      withOffline(() => listTrainingJobs(id), MOCK_TRAINING_JOBS),
      withOffline(() => listEvaluations(id), MOCK_EVALUATIONS),
      withOffline(() => getUsageSummary(id), MOCK_USAGE_SUMMARY),
    ],
  );

  const offline =
    projectResult.offline ||
    specsResult.offline ||
    jobsResult.offline ||
    evalsResult.offline ||
    usageResult.offline;

  const specs: IntelligenceSpec[] = specsResult.data;
  const jobs: TrainingJob[] = jobsResult.data;
  const evaluations: Evaluation[] = evalsResult.data;
  const usage: UsageSummary = usageResult.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href="/projects"
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All projects
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
              {project.name}
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
              {project.description ?? "No description yet."}
            </p>
          </div>
          <StatusBadge status={project.status} />
        </div>
        <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-muted-ink">Project ID</dt>
            <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
              {project.id}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Created</dt>
            <dd className="mt-1 text-charcoal">
              {formatDateTime(project.created_at)}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Last updated</dt>
            <dd className="mt-1 text-charcoal">
              {formatDateTime(project.updated_at)}
            </dd>
          </div>
        </dl>
      </div>

      <div className="mt-8">
        <TerminationDemoButton projectId={id} />
      </div>

      <Section
        id="specs-heading"
        title="Intelligence specs"
        action={
          <Link
            href={`/projects/${id}/specs/new`}
            className="inline-flex min-h-[44px] cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-paper px-4 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
          >
            New spec
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        }
      >
        {specs.length === 0 ? (
          <EmptyState text="No specs yet. Describe a problem to start fabricating its intelligence." />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {specs.map((spec) => (
              <li key={spec.id}>
                <Link
                  href={`/projects/${id}/specs/${spec.id}`}
                  className="block h-full rounded-xl border border-line bg-card p-5 transition-all duration-200 hover:border-charcoal hover:shadow-[0_4px_6px_rgba(0,0,0,0.1)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-display text-lg font-bold text-charcoal">
                      {spec.name}
                    </h3>
                    <StatusPill status={spec.status} />
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-ink">
                    {spec.problem_statement}
                  </p>
                  <p className="mt-3 text-xs font-semibold tracking-wide text-muted-ink uppercase">
                    Primitive: {spec.intelligence_primitive.replace(/_/g, " ")}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <Link
          href={`/projects/${id}/datasets`}
          className="mt-4 inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-line bg-card px-4 py-2.5 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
        >
          <Database className="h-4 w-4" aria-hidden="true" />
          Datasets
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </Section>

      <Section id="jobs-heading" title="Training jobs">
        {jobs.length === 0 ? (
          <EmptyState text="No training jobs yet. Jobs appear here when a strategy is scheduled for execution." />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line bg-card">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-platinum/40 text-xs tracking-wide text-muted-ink uppercase">
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Job
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Updated
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="border-b border-line transition-colors duration-200 last:border-0 hover:bg-platinum/30"
                  >
                    <td className="px-4 py-3 font-semibold text-charcoal">
                      <Link
                        href={`/projects/${id}/jobs/${job.id}`}
                        aria-label={`View training job ${job.name}`}
                        className="rounded underline decoration-platinum-deep underline-offset-4 transition-colors duration-200 hover:decoration-charcoal"
                      >
                        {job.name}
                      </Link>
                      {job.error && (
                        <span className="mt-1 block max-w-xs text-xs font-normal text-[#8f1d1d]">
                          {job.error}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill status={job.status} />
                    </td>
                    <td className="px-4 py-3 text-muted-ink">
                      {formatDateTime(job.updated_at)}
                    </td>
                    <td className="px-4 py-3">
                      <JobTransitionButtons
                        jobId={job.id}
                        status={job.status}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section id="evaluations-heading" title="Evaluations">
        {evaluations.length === 0 ? (
          <EmptyState text="No evaluations yet. Run a baseline evaluation from a spec to set the bar to beat." />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {evaluations.map((evaluation) => (
              <li
                key={evaluation.id}
                className="rounded-xl border border-line bg-card p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-display text-base font-bold text-charcoal">
                    {evaluation.name}
                  </h3>
                  <StatusPill status={evaluation.status} />
                </div>
                <p className="mt-1 text-xs text-muted-ink">
                  {formatDateTime(evaluation.created_at)}
                </p>
                {evaluation.results && (
                  <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-line pt-3 text-sm">
                    <div>
                      <dt className="text-xs font-semibold text-muted-ink">
                        Best baseline
                      </dt>
                      <dd className="mt-0.5 font-semibold text-charcoal">
                        {evaluation.results.baselines.length > 0
                          ? evaluation.results.baselines.reduce((a, b) =>
                              (b.accuracy ?? -1) > (a.accuracy ?? -1) ? b : a,
                            ).name
                          : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-semibold text-muted-ink">
                        Bar to beat
                      </dt>
                      <dd className="mt-0.5 font-semibold text-charcoal">
                        {formatPercent(evaluation.results.bar_to_beat.accuracy)}{" "}
                        accuracy
                      </dd>
                    </div>
                  </dl>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="usage-heading" title="Usage">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-line bg-card p-5">
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              Total cost
            </p>
            <p className="mt-2 font-display text-3xl font-bold text-charcoal">
              ${usage.total_cost_usd.toFixed(2)}
            </p>
          </div>
          <div className="rounded-xl border border-line bg-card p-5">
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              Events recorded
            </p>
            <p className="mt-2 font-display text-3xl font-bold text-charcoal">
              {usage.event_count}
            </p>
          </div>
          <div className="rounded-xl border border-line bg-card p-5">
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              By kind
            </p>
            <ul className="mt-2 space-y-1 text-sm text-charcoal">
              {Object.entries(usage.by_kind).length === 0 ? (
                <li className="text-muted-ink">No usage yet.</li>
              ) : (
                Object.entries(usage.by_kind).map(([kind, cost]) => (
                  <li key={kind} className="flex justify-between gap-2">
                    <span>{kind}</span>
                    <span className="font-semibold">${cost.toFixed(2)}</span>
                  </li>
                ))
              )}
            </ul>
          </div>
          <div className="rounded-xl border border-line bg-card p-5">
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              By scope
            </p>
            <ul className="mt-2 space-y-1 text-sm text-charcoal">
              {Object.entries(usage.by_scope).length === 0 ? (
                <li className="text-muted-ink">No usage yet.</li>
              ) : (
                Object.entries(usage.by_scope).map(([scope, cost]) => (
                  <li key={scope} className="flex justify-between gap-2">
                    <span>{scope.replace(/_/g, " ")}</span>
                    <span className="font-semibold">${cost.toFixed(2)}</span>
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>
      </Section>
    </div>
  );
}
