import { AlertTriangle, ArrowLeft, Cloud, HardDrive } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type {
  JobStatus,
  TrainingJob,
  TrainingRun,
} from "../../../../../../shared/types";
import { OfflineBanner } from "../../../../../components/OfflineBanner";
import { RunAttemptSelector } from "../../../../../components/RunAttemptSelector";
import { RunControlButtons } from "../../../../../components/RunControlButtons";
import { RunLogViewer } from "../../../../../components/RunLogViewer";
import { RunMetricsPanel } from "../../../../../components/RunMetricsPanel";
import { StatusPill } from "../../../../../components/StatusPill";
import {
  getRunArtifacts,
  getRunCheckpoints,
  getRunCost,
  getTrainingJob,
  isApiOfflineError,
  listTrainingRuns,
  MOCK_RUN_ARTIFACTS,
  MOCK_RUN_CHECKPOINTS,
  MOCK_RUN_COST,
  MOCK_TRAINING_JOBS,
  MOCK_TRAINING_RUNS,
} from "../../../../../lib/api";

export const metadata: Metadata = {
  title: "Training job detail",
  description: "Rustenwer training job detail with live run controls.",
};

/** Always render on demand: run state, logs and metrics must be fresh. */
export const dynamic = "force-dynamic";

const TERMINAL_STATUSES: JobStatus[] = ["FAILED", "CANCELLED", "COMPLETED"];

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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit] ?? "B"}`;
}

function formatUsd(value: number): string {
  return `$${value.toFixed(4)}`;
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

function ProviderBadge({ provider }: { provider: string }) {
  const Icon = provider === "digitalocean" ? Cloud : HardDrive;
  return (
    <span className="inline-flex min-h-[28px] items-center gap-1.5 rounded-full bg-platinum-deep px-3 py-1 text-xs font-semibold tracking-wide text-charcoal uppercase">
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {provider}
    </span>
  );
}

export default async function JobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; jobId: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const { id, jobId } = await params;
  const { run: runParam } = await searchParams;

  const jobResult = await withOffline(() => getTrainingJob(jobId), null);
  const job: TrainingJob | null = jobResult.offline
    ? (MOCK_TRAINING_JOBS.find((j) => j.id === jobId) ?? null)
    : jobResult.data;
  if (!job) notFound();

  const runsResult = await withOffline(
    () => listTrainingRuns(jobId),
    MOCK_TRAINING_RUNS.filter((r) => r.job_id === jobId),
  );
  const runs: TrainingRun[] = [...runsResult.data].sort(
    (a, b) => b.attempt - a.attempt,
  );
  const selected: TrainingRun | null =
    runs.find((r) => r.id === runParam) ?? runs[0] ?? null;

  const offline = jobResult.offline || runsResult.offline;

  const checkpointsResult = selected
    ? await withOffline(
        () => getRunCheckpoints(jobId, selected.id),
        MOCK_RUN_CHECKPOINTS[selected.id] ?? [],
      )
    : { data: [], offline };
  const artifactsResult = selected
    ? await withOffline(
        () => getRunArtifacts(jobId, selected.id),
        MOCK_RUN_ARTIFACTS[selected.id] ?? [],
      )
    : { data: [], offline };
  const costResult = selected
    ? await withOffline(
        () => getRunCost(jobId, selected.id),
        MOCK_RUN_COST[selected.id] ?? null,
      )
    : { data: null, offline };

  const checkpoints = [...checkpointsResult.data].sort(
    (a, b) => b.step - a.step,
  );
  const artifacts = artifactsResult.data;
  const cost = costResult.data;
  const allOffline =
    offline &&
    checkpointsResult.offline &&
    artifactsResult.offline &&
    costResult.offline;

  const strategy = job.strategy;
  const hyperparameterEntries = strategy
    ? Object.entries(strategy.hyperparameters)
    : [];
  const canEnqueue =
    selected === null || TERMINAL_STATUSES.includes(selected.status);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/projects/${id}`}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to project
      </Link>

      {allOffline && (
        <div className="mt-4">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-4 rounded-xl border border-line bg-card p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
              {job.name}
            </h1>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusPill status={job.status} />
              {selected && <ProviderBadge provider={selected.provider} />}
            </div>
          </div>
        </div>

        {strategy ? (
          <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm sm:grid-cols-3">
            <div>
              <dt className="font-semibold text-muted-ink">Training method</dt>
              <dd className="mt-1 font-mono text-[13px] text-charcoal">
                {strategy.training_method ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-muted-ink">Objective</dt>
              <dd className="mt-1 line-clamp-3 text-charcoal">
                {strategy.objective}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-muted-ink">Cost so far</dt>
              <dd className="mt-1 font-display text-2xl font-bold text-charcoal">
                {cost ? formatUsd(cost.usd) : "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="mt-6 border-t border-line pt-6 text-sm text-muted-ink">
            No training strategy recorded for this job yet.
          </p>
        )}

        {hyperparameterEntries.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              Key hyperparameters
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {hyperparameterEntries.slice(0, 5).map(([key, value]) => (
                <li
                  key={key}
                  className="rounded-lg bg-platinum px-2.5 py-1 font-mono text-xs text-charcoal"
                >
                  {key}={formatScalar(value)}
                </li>
              ))}
              {hyperparameterEntries.length > 5 && (
                <li className="rounded-lg bg-platinum px-2.5 py-1 font-mono text-xs text-muted-ink">
                  +{hyperparameterEntries.length - 5} more
                </li>
              )}
            </ul>
          </div>
        )}

        {job.error && (
          <p
            role="alert"
            className="mt-6 flex items-start gap-2 rounded-lg border border-[#DC2626]/30 bg-[#DC2626]/10 px-4 py-3 text-sm font-medium text-[#8f1d1d]"
          >
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0"
              aria-hidden="true"
            />
            {job.error}
          </p>
        )}
      </div>

      <Section
        id="runs-heading"
        title="Runs"
        action={
          <RunAttemptSelector
            projectId={id}
            jobId={jobId}
            runs={runs}
            selectedRunId={selected?.id ?? ""}
          />
        }
      >
        {selected === null ? (
          <>
            <EmptyState text="No runs yet — enqueue the first run below." />
            <div className="mt-4">
              <RunControlButtons
                jobId={jobId}
                runId={null}
                runStatus={null}
                checkpoints={[]}
                canEnqueue={canEnqueue}
                hasStrategy={strategy !== null}
              />
            </div>
          </>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-display text-lg font-bold text-charcoal">
                Attempt {selected.attempt}
              </h3>
              <StatusPill status={selected.status} />
              <ProviderBadge provider={selected.provider} />
              <span className="text-xs text-muted-ink">
                Started{" "}
                {selected.started_at
                  ? formatDateTime(selected.started_at)
                  : "—"}
                {selected.finished_at &&
                  ` · finished ${formatDateTime(selected.finished_at)}`}
              </span>
            </div>
            {selected.error && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-[#DC2626]/30 bg-[#DC2626]/10 px-4 py-3 text-sm font-medium text-[#8f1d1d]"
              >
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0"
                  aria-hidden="true"
                />
                {selected.error}
              </p>
            )}
            <RunControlButtons
              jobId={jobId}
              runId={selected.id}
              runStatus={selected.status}
              checkpoints={checkpoints}
              canEnqueue={canEnqueue}
              hasStrategy={strategy !== null}
            />
          </div>
        )}
      </Section>

      {selected && (
        <>
          <Section id="logs-heading" title="Logs">
            <RunLogViewer jobId={jobId} runId={selected.id} />
          </Section>

          <Section id="metrics-heading" title="Metrics">
            <RunMetricsPanel
              jobId={jobId}
              runId={selected.id}
              runStatus={selected.status}
            />
          </Section>

          <div className="grid gap-10 lg:grid-cols-2">
            <Section id="checkpoints-heading" title="Checkpoints">
              {checkpoints.length === 0 ? (
                <EmptyState text="No checkpoints yet. They appear as the run saves them." />
              ) : (
                <>
                  <div className="overflow-x-auto rounded-xl border border-line bg-card">
                    <table className="w-full min-w-[480px] text-left text-sm">
                      <thead>
                        <tr className="border-b border-line bg-platinum/40 text-xs tracking-wide text-muted-ink uppercase">
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Checkpoint
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Epoch
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Step
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Size
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Created
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {checkpoints.map((ckpt, index) => (
                          <tr
                            key={ckpt.id}
                            className="border-b border-line transition-colors duration-200 last:border-0 hover:bg-platinum/30"
                          >
                            <td className="px-4 py-3 font-mono text-[13px] font-semibold text-charcoal">
                              {ckpt.id}
                              {index === 0 && (
                                <span className="ml-2 rounded-full bg-charcoal px-2 py-0.5 text-[10px] font-bold tracking-wide text-platinum uppercase">
                                  Latest
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-charcoal">
                              {ckpt.epoch}
                            </td>
                            <td className="px-4 py-3 text-charcoal">
                              {ckpt.step}
                            </td>
                            <td className="px-4 py-3 text-charcoal">
                              {formatBytes(ckpt.bytes)}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap text-muted-ink">
                              {formatDateTime(ckpt.created_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-xs text-muted-ink">
                    Resume-from-checkpoint is an enqueue option — pick a
                    checkpoint in the Enqueue form above to start a new attempt
                    from it.
                  </p>
                </>
              )}
            </Section>

            <Section id="artifacts-heading" title="Artifacts">
              {artifacts.length === 0 ? (
                <EmptyState text="No artifacts yet. They are registered when the run publishes them." />
              ) : (
                <div className="overflow-x-auto rounded-xl border border-line bg-card">
                  <table className="w-full min-w-[480px] text-left text-sm">
                    <thead>
                      <tr className="border-b border-line bg-platinum/40 text-xs tracking-wide text-muted-ink uppercase">
                        <th scope="col" className="px-4 py-3 font-semibold">
                          Name
                        </th>
                        <th scope="col" className="px-4 py-3 font-semibold">
                          Version
                        </th>
                        <th scope="col" className="px-4 py-3 font-semibold">
                          SHA-256
                        </th>
                        <th scope="col" className="px-4 py-3 font-semibold">
                          Size
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {artifacts.map((artifact) => (
                        <tr
                          key={`${artifact.name}-v${artifact.version}`}
                          className="border-b border-line transition-colors duration-200 last:border-0 hover:bg-platinum/30"
                        >
                          <td className="px-4 py-3 font-semibold text-charcoal">
                            {artifact.name}
                          </td>
                          <td className="px-4 py-3 text-charcoal">
                            v{artifact.version}
                          </td>
                          <td
                            className="px-4 py-3 font-mono text-xs text-muted-ink"
                            title={artifact.sha256}
                          >
                            {artifact.sha256.slice(0, 12)}…
                          </td>
                          <td className="px-4 py-3 text-charcoal">
                            {formatBytes(artifact.bytes)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>
          </div>

          <Section id="cost-heading" title="Cost">
            {cost ? (
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-line bg-card p-5">
                  <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                    Elapsed
                  </p>
                  <p className="mt-2 font-display text-3xl font-bold text-charcoal">
                    {cost.seconds.toLocaleString()}s
                  </p>
                  <p className="mt-1 text-xs text-muted-ink">
                    provider: {cost.provider}
                  </p>
                </div>
                <div className="rounded-xl border border-line bg-card p-5">
                  <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                    Rate
                  </p>
                  <p className="mt-2 font-display text-3xl font-bold text-charcoal">
                    ${cost.rate_usd_per_hour.toFixed(2)}
                    <span className="text-base font-semibold text-muted-ink">
                      /h
                    </span>
                  </p>
                </div>
                <div className="rounded-xl border border-line bg-card p-5">
                  <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                    Total
                  </p>
                  <p className="mt-2 font-display text-3xl font-bold text-charcoal">
                    {formatUsd(cost.usd)}
                  </p>
                </div>
              </div>
            ) : (
              <EmptyState text="No cost data for this run yet." />
            )}
          </Section>
        </>
      )}
    </div>
  );
}
