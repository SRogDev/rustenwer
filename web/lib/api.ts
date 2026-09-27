/**
 * Typed API client for the Rustenwer backend (Phase 0).
 *
 * Contract mirror of `shared/README.md`. Domain types are imported from the
 * single source of truth (`shared/types.ts`) with `import type`, which is
 * erased at build time — no bundler path issues.
 *
 * Mock fallback: when the API is unreachable, the client throws
 * `ApiOfflineError`. Callers catch it and render the labeled mock dataset so
 * Phase 0 can be demoed before the backend is running.
 */
import type {
  ArtifactRecord,
  Benchmark,
  CheckpointInfo,
  ComparisonReport,
  Dataset,
  DatasetReport,
  DatasetVersion,
  Deployment,
  DeploymentStatus,
  DiagnosisResult,
  Evaluation,
  EvaluationRun,
  Intelligence,
  IntelligencePrimitive,
  IntelligenceSpec,
  IntelligenceVersion,
  JobStatus,
  MetricSeries,
  Model,
  ModelVersion,
  Project,
  ProjectStatus,
  QualityVector,
  RunCost,
  RunMetrics,
  SubjectKind,
  TrainingJob,
  TrainingRun,
  TrainingStrategy,
  UsageEvent,
  UsageKind,
  UsageRollups,
  UsageScope,
  UsageSummary,
} from "../../shared/types";

/** Re-exported so consumers can keep importing from the client module. */
export type { ScopeRollup, UsageRollups } from "../../shared/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Phase 0 stub auth: any well-formed Bearer token is accepted by the API.
 * Exported so raw-fetch clients (the SSE log viewer, which cannot use
 * request() — EventSource/fetch streaming has no place for its timeout)
 * can attach the same Authorization header.
 */
export const DEV_TOKEN = "phase0-dev-token";

export class ApiOfflineError extends Error {
  constructor(message = "API unreachable") {
    super(message);
    this.name = "ApiOfflineError";
  }
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

const REQUEST_TIMEOUT_MS = 8000;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${DEV_TOKEN}`,
        ...(options.headers ?? {}),
      },
    });
    if (!res.ok) {
      let detail = `Request failed with status ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // keep default detail
      }
      throw new ApiError(res.status, detail);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiOfflineError(
      `Could not reach ${API_BASE_URL}${path}: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    clearTimeout(timeout);
  }
}

export function isApiOfflineError(err: unknown): err is ApiOfflineError {
  return err instanceof ApiOfflineError;
}

export async function checkHealth(): Promise<{
  status: string;
  service: string;
  version: string;
}> {
  return request("/health");
}

export async function listProjects(): Promise<Project[]> {
  return request<Project[]>("/api/v1/projects");
}

export async function getProject(id: string): Promise<Project> {
  return request<Project>(`/api/v1/projects/${encodeURIComponent(id)}`);
}

export async function createProject(input: {
  name: string;
  description?: string;
}): Promise<Project> {
  return request<Project>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateProject(
  id: string,
  input: Partial<Pick<Project, "name" | "description" | "status">>,
): Promise<Project> {
  return request<Project>(`/api/v1/projects/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

/** Soft-archives a project (DELETE → status ARCHIVED). */
export async function archiveProject(id: string): Promise<void> {
  await request<void>(`/api/v1/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Mock fallback dataset (Phase 0 demo only).
// Served ONLY when the API is unreachable; the UI labels it as mock data.
// ---------------------------------------------------------------------------

const MOCK_ORG_ID = "00000000-0000-0000-0000-000000000001";

export const MOCK_PROJECTS: Project[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    organization_id: MOCK_ORG_ID,
    name: "Support triage classifier",
    description:
      "Classify incoming support tickets into refund, bug, or how-to, and route each to the right queue.",
    status: "ACTIVE" satisfies ProjectStatus,
    created_by: null,
    created_at: "2026-09-20T14:32:00Z",
    updated_at: "2026-09-25T09:12:00Z",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    organization_id: MOCK_ORG_ID,
    name: "Invoice anomaly detector",
    description:
      "Flag supplier invoices whose amounts deviate from historical patterns before they are paid.",
    status: "PAUSED" satisfies ProjectStatus,
    created_by: null,
    created_at: "2026-09-22T10:05:00Z",
    updated_at: "2026-09-24T17:48:00Z",
  },
  {
    id: "33333333-3333-3333-3333-333333333333",
    organization_id: MOCK_ORG_ID,
    name: "Lead scoring ranker",
    description:
      "Rank inbound leads by likelihood to convert so sales calls the hottest first.",
    status: "ACTIVE" satisfies ProjectStatus,
    created_by: null,
    created_at: "2026-09-25T08:20:00Z",
    updated_at: "2026-09-26T03:15:00Z",
  },
];

// ---------------------------------------------------------------------------
// Phase 1 — MVP core clients.
// Contract: `shared/README.md` "Phase 1 — MVP core" table.
// Types imported from `shared/types.ts` (single source of truth).
// ---------------------------------------------------------------------------

/** Payload for POST /api/v1/projects/{id}/specs. */
export interface CreateSpecInput {
  name: string;
  description?: string;
  problem_statement: string;
  /**
   * Omit to let the Diagnostic Agent auto-detect the primitive from the
   * problem statement (keyword map in `shared/services/diagnosis.py`).
   */
  intelligence_primitive?: IntelligencePrimitive;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  quality_requirements?: Record<string, unknown>;
  latency_requirements?: { latency_budget_ms: number | null };
  cost_requirements?: Record<string, unknown>;
  memory_requirements?: Record<string, unknown>;
  reliability_requirements?: Record<string, unknown>;
  deployment_requirements?: Record<string, unknown>;
  constraints?: string[];
  available_data?: string;
  evaluation_definition?: string;
  human_review_policy?: string;
}

export async function listSpecs(
  projectId: string,
): Promise<IntelligenceSpec[]> {
  return request<IntelligenceSpec[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/specs`,
  );
}

export async function createSpec(
  projectId: string,
  input: CreateSpecInput,
): Promise<IntelligenceSpec> {
  return request<IntelligenceSpec>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/specs`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getSpec(specId: string): Promise<IntelligenceSpec> {
  return request<IntelligenceSpec>(
    `/api/v1/specs/${encodeURIComponent(specId)}`,
  );
}

export async function patchSpec(
  specId: string,
  input: Partial<CreateSpecInput>,
): Promise<IntelligenceSpec> {
  return request<IntelligenceSpec>(
    `/api/v1/specs/${encodeURIComponent(specId)}`,
    { method: "PATCH", body: JSON.stringify(input) },
  );
}

/** Runs the Specification/Diagnostic Agent → DiagnosisResult (status → DIAGNOSED). */
export async function diagnoseSpec(specId: string): Promise<DiagnosisResult> {
  return request<DiagnosisResult>(
    `/api/v1/specs/${encodeURIComponent(specId)}/diagnose`,
    { method: "POST" },
  );
}

/** DRAFT/DIAGNOSED → APPROVED (409 otherwise). */
export async function approveSpec(specId: string): Promise<IntelligenceSpec> {
  return request<IntelligenceSpec>(
    `/api/v1/specs/${encodeURIComponent(specId)}/approve`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------

export interface CreateDatasetInput {
  name: string;
  description?: string;
  format?: Dataset["format"];
}

export async function listDatasets(projectId: string): Promise<Dataset[]> {
  return request<Dataset[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/datasets`,
  );
}

export async function createDataset(
  projectId: string,
  input: CreateDatasetInput,
): Promise<Dataset> {
  return request<Dataset>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/datasets`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  return request<Dataset>(`/api/v1/datasets/${encodeURIComponent(datasetId)}`);
}

export interface CreateDatasetVersionInput {
  rows: Record<string, unknown>[];
  label_column?: string;
}

/** Creates a version: validates rows and computes the DatasetReport. */
export async function createDatasetVersion(
  datasetId: string,
  input: CreateDatasetVersionInput,
): Promise<DatasetVersion> {
  return request<DatasetVersion>(
    `/api/v1/datasets/${encodeURIComponent(datasetId)}/versions`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function listDatasetVersions(
  datasetId: string,
): Promise<DatasetVersion[]> {
  return request<DatasetVersion[]>(
    `/api/v1/datasets/${encodeURIComponent(datasetId)}/versions`,
  );
}

export async function getDatasetVersion(
  datasetId: string,
  version: number,
): Promise<DatasetVersion> {
  return request<DatasetVersion>(
    `/api/v1/datasets/${encodeURIComponent(datasetId)}/versions/${version}`,
  );
}

/** Recomputes the validation report for an existing version. */
export async function validateDatasetVersion(
  datasetId: string,
  version: number,
): Promise<DatasetReport> {
  return request<DatasetReport>(
    `/api/v1/datasets/${encodeURIComponent(datasetId)}/versions/${version}/validate`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------

export interface CreateTrainingJobInput {
  name: string;
  spec_id?: string;
  dataset_version_id?: string;
  strategy?: TrainingStrategy;
  compute_budget?: TrainingJob["compute_budget"];
}

export async function listTrainingJobs(
  projectId: string,
): Promise<TrainingJob[]> {
  return request<TrainingJob[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/training-jobs`,
  );
}

export async function createTrainingJob(
  projectId: string,
  input: CreateTrainingJobInput,
): Promise<TrainingJob> {
  return request<TrainingJob>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/training-jobs`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getTrainingJob(jobId: string): Promise<TrainingJob> {
  return request<TrainingJob>(
    `/api/v1/training-jobs/${encodeURIComponent(jobId)}`,
  );
}

/** Transitions a job (409 on invalid transition, plan §42). */
export async function transitionTrainingJob(
  jobId: string,
  to: JobStatus,
): Promise<TrainingJob> {
  return request<TrainingJob>(
    `/api/v1/training-jobs/${encodeURIComponent(jobId)}/transition`,
    { method: "POST", body: JSON.stringify({ to }) },
  );
}

/** Empty until Phase 2 executes real runs. */
export async function listTrainingRuns(jobId: string): Promise<TrainingRun[]> {
  return request<TrainingRun[]>(
    `/api/v1/training-jobs/${encodeURIComponent(jobId)}/runs`,
  );
}

// ---------------------------------------------------------------------------
// Phase 2 — training run execution clients (plan §12 executor).
// Contract: the backend implements these endpoints in parallel; the shapes
// below are FINAL per the phase-2 contract (see shared/types.ts).
// All paths are bearer-authenticated and org-scoped.
// ---------------------------------------------------------------------------

/** Compute provider accepted by POST …/enqueue. */
export type TrainingProvider = "local" | "digitalocean";

/** Payload for POST /api/v1/training-jobs/{jobId}/enqueue. */
export interface EnqueueRunInput {
  provider?: TrainingProvider;
  hyperparameters?: Record<string, unknown>;
  resume_from_checkpoint_id?: string | null;
}

/**
 * Enqueues a new execution attempt of a job → 201 TrainingRun.
 * 409 on missing/invalid strategy, illegal job state, or qlora on the
 * local provider (the `detail` is surfaced inline by the UI).
 */
export async function enqueueTrainingJob(
  jobId: string,
  input: EnqueueRunInput,
): Promise<TrainingRun> {
  return request<TrainingRun>(
    `/api/v1/training-jobs/${encodeURIComponent(jobId)}/enqueue`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getTrainingRun(
  jobId: string,
  runId: string,
): Promise<TrainingRun> {
  return request<TrainingRun>(
    `/api/v1/training-jobs/${encodeURIComponent(jobId)}/runs/${encodeURIComponent(runId)}`,
  );
}

function runActionPath(jobId: string, runId: string, action: string): string {
  return `/api/v1/training-jobs/${encodeURIComponent(jobId)}/runs/${encodeURIComponent(runId)}/${action}`;
}

export async function pauseRun(
  jobId: string,
  runId: string,
): Promise<TrainingRun> {
  return request<TrainingRun>(runActionPath(jobId, runId, "pause"), {
    method: "POST",
  });
}

export async function resumeRun(
  jobId: string,
  runId: string,
): Promise<TrainingRun> {
  return request<TrainingRun>(runActionPath(jobId, runId, "resume"), {
    method: "POST",
  });
}

export async function cancelRun(
  jobId: string,
  runId: string,
): Promise<TrainingRun> {
  return request<TrainingRun>(runActionPath(jobId, runId, "cancel"), {
    method: "POST",
  });
}

/** Starts a new attempt; from_checkpoint resumes from the latest checkpoint. */
export async function retryRun(
  jobId: string,
  runId: string,
  input: { from_checkpoint?: boolean } = {},
): Promise<TrainingRun> {
  return request<TrainingRun>(runActionPath(jobId, runId, "retry"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getRunMetrics(
  jobId: string,
  runId: string,
): Promise<RunMetrics> {
  return request<RunMetrics>(runActionPath(jobId, runId, "metrics"));
}

export async function getRunCheckpoints(
  jobId: string,
  runId: string,
): Promise<CheckpointInfo[]> {
  return request<CheckpointInfo[]>(runActionPath(jobId, runId, "checkpoints"));
}

export async function getRunArtifacts(
  jobId: string,
  runId: string,
): Promise<ArtifactRecord[]> {
  return request<ArtifactRecord[]>(runActionPath(jobId, runId, "artifacts"));
}

export async function getRunCost(
  jobId: string,
  runId: string,
): Promise<RunCost> {
  return request<RunCost>(runActionPath(jobId, runId, "cost"));
}

/**
 * URL builder for the run log stream.
 * The viewer fetches this with raw fetch() + a ReadableStream reader so the
 * Bearer token can be sent (EventSource cannot send Authorization headers);
 * never pass this URL through request() — its timeout would abort the
 * long-lived stream.
 */
export function runLogsUrl(jobId: string, runId: string, tail = 300): string {
  const params = new URLSearchParams({ tail: String(tail), follow: "true" });
  return `${API_BASE_URL}/api/v1/training-jobs/${encodeURIComponent(jobId)}/runs/${encodeURIComponent(runId)}/logs?${params.toString()}`;
}

// ---------------------------------------------------------------------------

export interface CreateModelInput {
  name: string;
  description?: string;
}

export async function listModels(projectId: string): Promise<Model[]> {
  return request<Model[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/models`,
  );
}

export async function createModel(
  projectId: string,
  input: CreateModelInput,
): Promise<Model> {
  return request<Model>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/models`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export interface CreateModelVersionInput {
  training_run_id?: string;
  architecture?: Record<string, unknown>;
  size_bytes?: number;
  metrics?: Record<string, unknown>;
  artifact_uri?: string;
}

export async function createModelVersion(
  modelId: string,
  input: CreateModelVersionInput,
): Promise<ModelVersion> {
  return request<ModelVersion>(
    `/api/v1/models/${encodeURIComponent(modelId)}/versions`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function listModelVersions(
  modelId: string,
): Promise<ModelVersion[]> {
  return request<ModelVersion[]>(
    `/api/v1/models/${encodeURIComponent(modelId)}/versions`,
  );
}

// ---------------------------------------------------------------------------

export interface RunEvaluationInput {
  name?: string;
  spec_id: string;
  dataset_version_id: string;
}

/** Runs the baselines synchronously → Evaluation (COMPLETED). */
export async function runEvaluation(
  projectId: string,
  input: RunEvaluationInput,
): Promise<Evaluation> {
  return request<Evaluation>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evaluations/run`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function listEvaluations(
  projectId: string,
): Promise<Evaluation[]> {
  return request<Evaluation[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evaluations`,
  );
}

export async function getEvaluation(evaluationId: string): Promise<Evaluation> {
  return request<Evaluation>(
    `/api/v1/evaluations/${encodeURIComponent(evaluationId)}`,
  );
}

// ---------------------------------------------------------------------------

export interface CreateDeploymentInput {
  name: string;
  spec_id: string;
  model_version_id?: string;
}

export async function listDeployments(
  projectId: string,
): Promise<Deployment[]> {
  return request<Deployment[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/deployments`,
  );
}

export async function createDeployment(
  projectId: string,
  input: CreateDeploymentInput,
): Promise<Deployment> {
  return request<Deployment>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/deployments`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function patchDeployment(
  deploymentId: string,
  input: { status: DeploymentStatus },
): Promise<Deployment> {
  return request<Deployment>(
    `/api/v1/deployments/${encodeURIComponent(deploymentId)}`,
    { method: "PATCH", body: JSON.stringify(input) },
  );
}

// ---------------------------------------------------------------------------

export interface RecordUsageEventInput {
  scope: UsageScope;
  scope_id: string;
  kind: UsageKind;
  quantity?: number;
  unit?: string;
  cost_usd?: number;
}

export async function recordUsageEvent(
  projectId: string,
  input: RecordUsageEventInput,
): Promise<UsageEvent> {
  return request<UsageEvent>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/usage-events`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getUsageSummary(
  projectId: string,
): Promise<UsageSummary> {
  return request<UsageSummary>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/usage/summary`,
  );
}

// ---------------------------------------------------------------------------

/** Seeds the §7 termination fixture and runs the baseline evaluation. */
export interface TerminationDemoResult {
  spec: IntelligenceSpec;
  dataset: Dataset;
  version: DatasetVersion;
  evaluation: Evaluation;
}

export async function runTerminationDemo(
  projectId: string,
): Promise<TerminationDemoResult> {
  return request<TerminationDemoResult>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/demo/termination`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------
// Mock fallback dataset (Phase 1 demo only).
// Served ONLY when the API is unreachable; the UI labels it as mock data.
// Consistent with the termination-intelligence fixture (plan §7 /
// shared/services/fixtures.py): spec "Search termination intelligence",
// primitive `termination`, latency budget 50ms, 12 labeled rows with
// majority_class ≈ 0.67 / keyword_heuristic ≈ 0.83 /
// deterministic_rule ≈ 0.92.
// ---------------------------------------------------------------------------

const MOCK_SPEC_ID = "44444444-4444-4444-4444-444444444444";
const MOCK_DATASET_ID = "55555555-5555-5555-5555-555555555555";
const MOCK_VERSION_ID = "66666666-6666-6666-6666-666666666666";

const NULL_REQUIREMENTS = {
  quality_requirements: null,
  latency_requirements: null,
  cost_requirements: null,
  memory_requirements: null,
  reliability_requirements: null,
  deployment_requirements: null,
} as const;

export const MOCK_SPECS: IntelligenceSpec[] = [
  {
    id: MOCK_SPEC_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    name: "Search termination intelligence",
    description:
      "Decide when an autonomous search has gathered enough and should stop.",
    problem_statement:
      "An autonomous research search explores sources looking for useful discoveries. After each step it must decide whether to continue searching or stop: stopping too early misses key findings, searching too long wastes budget. The decision must happen within 50 milliseconds so the search loop never stalls.",
    input_schema: { search_state: { type: "object" } },
    output_schema: {
      decision: { enum: ["continue", "stop"] },
      confidence: { type: "number" },
    },
    intelligence_primitive: "termination",
    quality_requirements: { objective: "maximize useful discoveries" },
    latency_requirements: { latency_budget_ms: 50 },
    cost_requirements: { max_cost_usd_per_1k_decisions: 0.01 },
    memory_requirements: null,
    reliability_requirements: null,
    constraints: [
      "decision latency under 50ms",
      "no external API calls at decision time",
    ],
    available_data:
      "12 labeled search-step examples (state summary, depth, progress score → continue/stop).",
    evaluation_definition:
      "Accuracy on held-out search steps, plus p50 latency under the 50ms budget.",
    deployment_requirements: null,
    human_review_policy: null,
    status: "DIAGNOSED" as const,
    version: 1,
  },
  {
    id: "77777777-7777-7777-7777-777777777777",
    project_id: "11111111-1111-1111-1111-111111111111",
    name: "Support ticket classifier",
    description: null,
    problem_statement:
      "Route each incoming support ticket to the right queue: refund, bug, or how-to.",
    input_schema: { ticket_text: { type: "string" } },
    output_schema: { category: { enum: ["refund", "bug", "how-to"] } },
    intelligence_primitive: "classification",
    ...NULL_REQUIREMENTS,
    constraints: [],
    available_data: null,
    evaluation_definition: null,
    human_review_policy: null,
    status: "DRAFT" as const,
    version: 1,
  },
];

export const MOCK_DATASETS: Dataset[] = [
  {
    id: MOCK_DATASET_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    name: "termination demo dataset",
    description:
      "12 labeled search steps from the §7 fixture: state summary, depth, progress score → continue/stop.",
    format: "inline",
    row_count: 12,
    created_at: "2026-09-26T09:55:00Z",
    updated_at: "2026-09-26T09:58:00Z",
  },
];

export const MOCK_DATASET_VERSIONS: DatasetVersion[] = [
  {
    id: MOCK_VERSION_ID,
    dataset_id: MOCK_DATASET_ID,
    version: 1,
    column_schema: {
      state_summary: "str",
      depth: "int",
      progress_score: "float",
      label: "str",
    },
    split_config: { train: 0.7, validation: 0.15, test: 0.15 },
    stats: {
      dataset_id: MOCK_DATASET_ID,
      version: 1,
      row_count: 12,
      column_schema: {
        state_summary: "str",
        depth: "int",
        progress_score: "float",
        label: "str",
      },
      class_balance: { continue: 8, stop: 4 },
      missing_values: {
        state_summary: 0,
        depth: 0,
        progress_score: 0,
        label: 0,
      },
      leakage_flags: [],
      imbalance_detected: false,
      recommended_split: { train: 0.7, validation: 0.15, test: 0.15 },
      ready_for_training: true,
      notes: ["MOCK validation report — served offline for demo purposes."],
    },
    created_at: "2026-09-26T09:58:00Z",
  },
];

export const MOCK_EVALUATIONS: Evaluation[] = [
  {
    id: "88888888-8888-8888-8888-888888888888",
    project_id: "11111111-1111-1111-1111-111111111111",
    spec_id: MOCK_SPEC_ID,
    dataset_version_id: MOCK_VERSION_ID,
    name: "Termination baseline evaluation",
    status: "COMPLETED",
    results: {
      baselines: [
        {
          name: "majority_class",
          description: "Always predict the most frequent label (continue).",
          accuracy: 0.6667,
          latency_ms_p50: 0.004,
          cost_usd_per_1k: 0,
          size_bytes: 64,
          predictions_evaluated: 12,
        },
        {
          name: "keyword_heuristic",
          description:
            "Predict stop when the state summary mentions stalled or exhausted progress, else continue.",
          accuracy: 0.8333,
          latency_ms_p50: 0.021,
          cost_usd_per_1k: 0,
          size_bytes: 512,
          predictions_evaluated: 12,
        },
        {
          name: "deterministic_rule",
          description:
            "Stop when progress_score >= 0.8 and depth >= 5; threshold found by exhaustive scan.",
          accuracy: 0.9167,
          latency_ms_p50: 0.012,
          cost_usd_per_1k: 0,
          size_bytes: 256,
          predictions_evaluated: 12,
        },
      ],
      bar_to_beat: {
        accuracy: 0.9167,
        latency_ms_p50: 0.012,
        cost_usd_per_1k: 0,
      },
      recommendation:
        "Promote the deterministic_rule baseline: 91.7% accuracy at zero inference cost with p50 latency far under the 50ms budget. Any trained candidate must beat this bar.",
      evaluated_at: "2026-09-26T10:00:00Z",
    },
    created_at: "2026-09-26T09:58:00Z",
    completed_at: "2026-09-26T10:00:00Z",
  },
];

export const MOCK_TRAINING_JOBS: TrainingJob[] = [
  {
    id: "99999999-9999-9999-9999-999999999999",
    project_id: "11111111-1111-1111-1111-111111111111",
    spec_id: MOCK_SPEC_ID,
    dataset_version_id: MOCK_VERSION_ID,
    name: "termination embedding-ft candidate",
    status: "RUNNING",
    strategy: {
      model_family: "small-encoder",
      architecture: { type: "embedding-classifier", hidden: 256 },
      training_method: "embedding-ft",
      objective: "maximize useful discoveries",
      dataset_ref: { dataset_id: MOCK_DATASET_ID, version: 1 },
      hyperparameters: { rank: 16, epochs: 3, lr: 2e-4 },
      evaluation_plan:
        "Accuracy on held-out search steps, plus p50 latency under the 50ms budget.",
      compute_budget: { max_gpu_hours: 0.5, max_cost_usd: 5.12 },
      baseline_bar: {
        accuracy: 0.9167,
        latency_ms_p50: 0.012,
        cost_usd_per_1k: 0,
      },
      rationale:
        "Learned policy for the termination decision; must beat the deterministic_rule baseline.",
      no_training_justification: null,
    },
    compute_budget: { max_gpu_hours: 0.5, max_cost_usd: 5.12 },
    error: null,
    created_at: "2026-09-26T10:05:00Z",
    updated_at: "2026-09-26T10:20:00Z",
  },
  {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    project_id: "11111111-1111-1111-1111-111111111111",
    spec_id: "77777777-7777-7777-7777-777777777777",
    dataset_version_id: null,
    name: "ticket classifier lora candidate",
    status: "CREATED",
    strategy: null,
    compute_budget: null,
    error: null,
    created_at: "2026-09-26T11:00:00Z",
    updated_at: "2026-09-26T11:00:00Z",
  },
];

export const MOCK_USAGE_SUMMARY: UsageSummary = {
  project_id: "11111111-1111-1111-1111-111111111111",
  total_cost_usd: 12.4,
  by_scope: { training_job: 12.4 },
  by_kind: { training: 12.4 },
  event_count: 7,
};

// ---------------------------------------------------------------------------
// Mock fallback dataset (Phase 2 demo only).
// Two attempts of the RUNNING mock job: attempt 1 FAILED (OOM), attempt 2
// RUNNING with a synthetic decaying loss curve.
// ---------------------------------------------------------------------------

const MOCK_RUN_ID_1 = "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1";
const MOCK_RUN_ID_2 = "c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2";
const MOCK_JOB_ID = "99999999-9999-9999-9999-999999999999";

export const MOCK_TRAINING_RUNS: TrainingRun[] = [
  {
    id: MOCK_RUN_ID_1,
    job_id: MOCK_JOB_ID,
    attempt: 1,
    status: "FAILED",
    provider: "local",
    metrics: {},
    artifacts: {},
    logs: null,
    error:
      "CUDA out of memory: tried to allocate 2.1 GiB on device 0. Reduce batch_size or enable gradient checkpointing.",
    started_at: "2026-09-26T10:21:00Z",
    finished_at: "2026-09-26T10:24:37Z",
  },
  {
    id: MOCK_RUN_ID_2,
    job_id: MOCK_JOB_ID,
    attempt: 2,
    status: "RUNNING",
    provider: "local",
    metrics: {},
    artifacts: {},
    logs: null,
    error: null,
    started_at: "2026-09-26T10:31:00Z",
    finished_at: null,
  },
];

/** Deterministic decaying loss curve for the mock RUNNING attempt. */
function mockLossSeries(): MetricSeries {
  const points = Array.from({ length: 48 }, (_, i) => {
    const step = (i + 1) * 25;
    const value = 2.4 * Math.exp(-step / 900) + 0.28 + 0.04 * Math.sin(i / 3);
    return {
      step,
      value: Math.round(value * 10000) / 10000,
      ts: new Date(Date.UTC(2026, 8, 26, 10, 31, 0) + i * 45000).toISOString(),
    };
  });
  return { name: "loss", points };
}

export const MOCK_RUN_METRICS: Record<string, RunMetrics> = {
  [MOCK_RUN_ID_2]: {
    run_id: MOCK_RUN_ID_2,
    series: [
      mockLossSeries(),
      {
        name: "lr",
        points: mockLossSeries().points.map((p) => ({
          step: p.step,
          value: 0.0002,
          ts: p.ts,
        })),
      },
      {
        name: "grad_norm",
        points: mockLossSeries().points.map((p, i) => ({
          step: p.step,
          value:
            Math.round(
              (1.8 * Math.exp(-p.step / 1400) + 0.35 + 0.05 * Math.sin(i / 2)) *
                10000,
            ) / 10000,
          ts: p.ts,
        })),
      },
    ],
    latest: {
      loss: 0.6124,
      lr: 0.0002,
      grad_norm: 0.8211,
      step: 1200,
      epoch: 2,
    },
  },
};

export const MOCK_RUN_CHECKPOINTS: Record<string, CheckpointInfo[]> = {
  [MOCK_RUN_ID_2]: [
    {
      id: "ckpt-0003",
      epoch: 2,
      step: 1200,
      bytes: 482344960,
      created_at: "2026-09-26T11:04:00Z",
    },
    {
      id: "ckpt-0002",
      epoch: 1,
      step: 800,
      bytes: 482344960,
      created_at: "2026-09-26T10:47:00Z",
    },
    {
      id: "ckpt-0001",
      epoch: 1,
      step: 400,
      bytes: 482344960,
      created_at: "2026-09-26T10:39:00Z",
    },
  ],
};

export const MOCK_RUN_ARTIFACTS: Record<string, ArtifactRecord[]> = {
  [MOCK_RUN_ID_2]: [
    {
      name: "encoder-adapter",
      version: 3,
      sha256:
        "9f2c4a7e1b5d83f06a4c2e9d1b7f5a3c8e6d2a1b4f7c9d3e5a6b8c1d2f4a7e9b",
      bytes: 482344960,
      created_at: "2026-09-26T11:04:12Z",
    },
    {
      name: "tokenizer",
      version: 1,
      sha256:
        "3a7d4e1f9b2c5a8d6e4f1a2b3c5d7e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d",
      bytes: 4194304,
      created_at: "2026-09-26T10:31:05Z",
    },
  ],
};

export const MOCK_RUN_COST: Record<string, RunCost> = {
  [MOCK_RUN_ID_2]: {
    run_id: MOCK_RUN_ID_2,
    provider: "local",
    seconds: 1830,
    usd: 1.2708,
    rate_usd_per_hour: 2.5,
  },
};

// ---------------------------------------------------------------------------
// Phase 3 — Evaluation & Registry clients.
// Contract: `shared/README.md` "Phase 3 — Evaluation & Registry" + "Cost"
// tables. The backend endpoints are finalized per the Phase 3 contract;
// types come from `shared/types.ts` (single source of truth).
// ---------------------------------------------------------------------------

/** Per-scope cost rollups (GET /api/v1/projects/{project_id}/usage/rollups). */
/** Contract: `shared/types.ts` (`ScopeRollup`, `UsageRollups`) — single source of truth. */

/** One subject for the compare endpoint. */
export interface CompareSubjectInput {
  kind: SubjectKind;
  ref?: string | null;
}

/** Payload for POST /api/v1/projects/{project_id}/benchmarks. */
export interface CreateBenchmarkInput {
  name: string;
  description?: string;
  input_spec?: Record<string, unknown>;
  expected_output?: Record<string, unknown>;
  evaluation_function?: string;
  dataset_version_id?: string | null;
  metrics?: string[];
  cost_rules?: Record<string, unknown>;
}

/** Seeded + project benchmarks. */
export async function listBenchmarks(projectId: string): Promise<Benchmark[]> {
  return request<Benchmark[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/benchmarks`,
  );
}

export async function createBenchmark(
  projectId: string,
  input: CreateBenchmarkInput,
): Promise<Benchmark> {
  return request<Benchmark>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/benchmarks`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getBenchmark(benchmarkId: string): Promise<Benchmark> {
  return request<Benchmark>(
    `/api/v1/benchmarks/${encodeURIComponent(benchmarkId)}`,
  );
}

// ---------------------------------------------------------------------------

/** Payload for POST /api/v1/benchmarks/{benchmark_id}/runs. */
export interface StartEvaluationRunInput {
  spec_id?: string | null;
  name?: string;
  subject: CompareSubjectInput;
}

/**
 * Starts an async evaluation of a subject on a benchmark → 201 EvaluationRun.
 * Subject kinds: 'baseline' (ref = baseline name), 'model_version'
 * (ref = model version id), 'reference' (ref = external reference id).
 */
export async function startEvaluationRun(
  benchmarkId: string,
  input: StartEvaluationRunInput,
): Promise<EvaluationRun> {
  return request<EvaluationRun>(
    `/api/v1/benchmarks/${encodeURIComponent(benchmarkId)}/runs`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function listEvaluationRuns(
  projectId: string,
): Promise<EvaluationRun[]> {
  return request<EvaluationRun[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evaluation-runs`,
  );
}

export async function getEvaluationRun(runId: string): Promise<EvaluationRun> {
  return request<EvaluationRun>(
    `/api/v1/evaluation-runs/${encodeURIComponent(runId)}`,
  );
}

/** Cancels a PENDING/RUNNING evaluation run → CANCELLED. */
export async function cancelEvaluationRun(
  runId: string,
): Promise<EvaluationRun> {
  return request<EvaluationRun>(
    `/api/v1/evaluation-runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );
}

/** Payload for POST /api/v1/benchmarks/{benchmark_id}/compare. */
export interface CompareBenchmarkInput {
  spec_id?: string | null;
  subjects: CompareSubjectInput[];
  incumbent_intelligence_version_id?: string | null;
}

/** Candidate vs baselines vs incumbent comparison → ComparisonReport. */
export async function compareBenchmark(
  benchmarkId: string,
  input: CompareBenchmarkInput,
): Promise<ComparisonReport> {
  return request<ComparisonReport>(
    `/api/v1/benchmarks/${encodeURIComponent(benchmarkId)}/compare`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

// ---------------------------------------------------------------------------

/** One model version with its lineage. */
export async function getModelVersion(
  modelId: string,
  version: number,
): Promise<ModelVersion> {
  return request<ModelVersion>(
    `/api/v1/models/${encodeURIComponent(modelId)}/versions/${version}`,
  );
}

/** One pairwise change between two model versions (backend shape). */
export interface ModelVersionChange {
  from_version: number;
  to_version: number;
  /** Names of the lineage fields that differ between the two versions. */
  changed_fields: string[];
}

/** Version chain + what changed between versions (backend shape). */
export interface ModelLineage {
  versions: ModelVersion[];
  changes: ModelVersionChange[];
}

export async function getModelLineage(modelId: string): Promise<ModelLineage> {
  return request<ModelLineage>(
    `/api/v1/models/${encodeURIComponent(modelId)}/lineage`,
  );
}

// ---------------------------------------------------------------------------

/** Payload for POST /api/v1/projects/{project_id}/intelligences. */
export interface CreateIntelligenceInput {
  name: string;
  description?: string;
  primitive?: Intelligence["primitive"];
}

export async function listIntelligences(
  projectId: string,
): Promise<Intelligence[]> {
  return request<Intelligence[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/intelligences`,
  );
}

export async function createIntelligence(
  projectId: string,
  input: CreateIntelligenceInput,
): Promise<Intelligence> {
  return request<Intelligence>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/intelligences`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getIntelligence(
  intelligenceId: string,
): Promise<Intelligence> {
  return request<Intelligence>(
    `/api/v1/intelligences/${encodeURIComponent(intelligenceId)}`,
  );
}

/** Payload for POST /api/v1/intelligences/{intelligence_id}/versions. */
export interface CreateIntelligenceVersionInput {
  components: Record<string, unknown>;
  notes?: string;
  best_evaluation_run_id?: string | null;
}

export async function listIntelligenceVersions(
  intelligenceId: string,
): Promise<IntelligenceVersion[]> {
  return request<IntelligenceVersion[]>(
    `/api/v1/intelligences/${encodeURIComponent(intelligenceId)}/versions`,
  );
}

export async function createIntelligenceVersion(
  intelligenceId: string,
  input: CreateIntelligenceVersionInput,
): Promise<IntelligenceVersion> {
  return request<IntelligenceVersion>(
    `/api/v1/intelligences/${encodeURIComponent(intelligenceId)}/versions`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getIntelligenceVersion(
  intelligenceId: string,
  version: number,
): Promise<IntelligenceVersion> {
  return request<IntelligenceVersion>(
    `/api/v1/intelligences/${encodeURIComponent(intelligenceId)}/versions/${version}`,
  );
}

/**
 * Promote an intelligence version.
 * Promotion logic lands in Phase 6: the backend answers 501. Callers should
 * catch ApiError and surface its detail honestly instead of hiding it.
 */
export async function promoteIntelligence(
  intelligenceId: string,
  input: { version?: number } = {},
): Promise<IntelligenceVersion> {
  return request<IntelligenceVersion>(
    `/api/v1/intelligences/${encodeURIComponent(intelligenceId)}/promote`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

// ---------------------------------------------------------------------------

/** Per-scope cost rollups (training_job, model, deployment, evaluation, inference). */
export async function getUsageRollups(
  projectId: string,
): Promise<UsageRollups> {
  return request<UsageRollups>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/usage/rollups`,
  );
}

// ---------------------------------------------------------------------------
// Mock fallback dataset (Phase 3 demo only).
// Served ONLY when the API is unreachable; the UI labels it as mock data.
// ---------------------------------------------------------------------------

const MOCK_BENCHMARK_TERMINATION_ID = "d3d3d3d3-d3d3-d3d3-d3d3-d3d3d3d3d3d3";
const MOCK_BENCHMARK_RING_ID = "e4e4e4e4-e4e4-e4e4-e4e4-e4e4e4e4e4e4";
const MOCK_MODEL_ID = "f5f5f5f5-f5f5-f5f5-f5f5-f5f5f5f5f5f5";
const MOCK_MODEL_V1_ID = "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1";
const MOCK_MODEL_V2_ID = "b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2";
const MOCK_INTELLIGENCE_ID = "c3c3c3c3-c3c3-c3c3-c3c3-c3c3c3c3c3c3";
const MOCK_EVAL_RUN_DONE_ID = "dd11dd11-dd11-dd11-dd11-dd11dd11dd11";
const MOCK_EVAL_RUN_RUNNING_ID = "ee22ee22-ee22-ee22-ee22-ee22ee22ee22";
const MOCK_EVAL_RUN_FAILED_ID = "ff33ff33-ff33-ff33-ff33-ff33ff33ff33";

export const MOCK_BENCHMARKS: Benchmark[] = [
  {
    id: MOCK_BENCHMARK_TERMINATION_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    name: "termination",
    description:
      "Seeded benchmark: decide when an autonomous search has gathered enough and should stop. 12 labeled search steps; the bar to beat is the deterministic_rule baseline at 91.7% accuracy.",
    input_spec: {
      search_state: { type: "object" },
      state_summary: { type: "string" },
      depth: { type: "integer" },
      progress_score: { type: "number" },
    },
    expected_output: {
      decision: { enum: ["continue", "stop"] },
      confidence: { type: "number" },
    },
    evaluation_function: "accuracy_on_labeled_steps",
    dataset_version_id: MOCK_VERSION_ID,
    metrics: ["accuracy", "latency_ms_p50", "cost_usd_per_1k"],
    cost_rules: { inference_cost_usd_per_1k: 0 },
    created_at: "2026-09-26T09:50:00Z",
  },
  {
    id: MOCK_BENCHMARK_RING_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    name: "ring",
    description:
      "Seeded benchmark: route inbound items around the ring topology with minimal hops and no dropped messages.",
    input_spec: { item: { type: "object" }, ring_state: { type: "object" } },
    expected_output: {
      next_hop: { type: "string" },
      drop: { type: "boolean" },
    },
    evaluation_function: "delivery_ratio_and_mean_hops",
    dataset_version_id: null,
    metrics: ["delivery_ratio", "mean_hops", "latency_ms_p50"],
    cost_rules: { inference_cost_usd_per_1k: 0 },
    created_at: "2026-09-26T09:50:00Z",
  },
];

const MOCK_QV_V2: QualityVector = {
  task_quality: 0.9583,
  calibration: 0.91,
  robustness: 0.88,
  latency_ms_p50: 0.31,
  latency_ms_p99: 1.2,
  inference_cost_usd_per_1k: 0.0004,
  training_cost_usd: 5.12,
  model_size_bytes: 482344960,
  reliability: 0.99,
};

export const MOCK_EVAL_RUNS: EvaluationRun[] = [
  {
    id: MOCK_EVAL_RUN_DONE_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    benchmark_id: MOCK_BENCHMARK_TERMINATION_ID,
    spec_id: MOCK_SPEC_ID,
    name: "termination classifier v2",
    subject: {
      kind: "model_version",
      ref: MOCK_MODEL_V2_ID,
      quality_vector: MOCK_QV_V2,
    },
    status: "COMPLETED",
    quality_vector: MOCK_QV_V2,
    metrics: { accuracy: 0.9583, evaluated_steps: 12 },
    cost_usd: 0.0042,
    error: null,
    created_at: "2026-09-26T12:05:00Z",
    completed_at: "2026-09-26T12:07:33Z",
  },
  {
    id: MOCK_EVAL_RUN_RUNNING_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    benchmark_id: MOCK_BENCHMARK_TERMINATION_ID,
    spec_id: MOCK_SPEC_ID,
    name: "deterministic_rule re-check",
    subject: {
      kind: "baseline",
      ref: "deterministic_rule",
      quality_vector: null,
    },
    status: "RUNNING",
    quality_vector: null,
    metrics: {},
    cost_usd: 0,
    error: null,
    created_at: "2026-09-26T12:30:00Z",
    completed_at: null,
  },
  {
    id: MOCK_EVAL_RUN_FAILED_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    benchmark_id: MOCK_BENCHMARK_RING_ID,
    spec_id: null,
    name: "ring heuristic attempt",
    subject: { kind: "baseline", ref: "greedy_ring", quality_vector: null },
    status: "FAILED",
    quality_vector: null,
    metrics: {},
    cost_usd: 0.0011,
    error:
      "evaluation_function crashed on row 7: 'next_hop' missing from subject output",
    created_at: "2026-09-26T13:00:00Z",
    completed_at: "2026-09-26T13:01:12Z",
  },
];

export const MOCK_MODELS: Model[] = [
  {
    id: MOCK_MODEL_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    name: "termination-embedding-classifier",
    description:
      "Learned policy for the search-termination decision; must beat the deterministic_rule baseline.",
    created_at: "2026-09-26T10:30:00Z",
  },
];

export const MOCK_MODEL_VERSIONS: ModelVersion[] = [
  {
    id: MOCK_MODEL_V1_ID,
    model_id: MOCK_MODEL_ID,
    version: 1,
    training_run_id: "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1",
    architecture: { type: "embedding-classifier", hidden: 128 },
    size_bytes: 241172480,
    metrics: { val_accuracy: 0.91 },
    artifact_uri: "artifacts://encoder-adapter/1",
    dataset_version_id: MOCK_VERSION_ID,
    training_strategy: { training_method: "embedding-ft", epochs: 2 },
    code_version: "rustenwer@a1b2c3",
    template_version: "trainer@1.0.0",
    seed: 7,
    base_model: "tiny-encoder-v1",
    lineage_locked: true,
    created_at: "2026-09-26T10:45:00Z",
  },
  {
    id: MOCK_MODEL_V2_ID,
    model_id: MOCK_MODEL_ID,
    version: 2,
    training_run_id: "c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2",
    architecture: { type: "embedding-classifier", hidden: 256 },
    size_bytes: 482344960,
    metrics: { val_accuracy: 0.9583 },
    artifact_uri: "artifacts://encoder-adapter/3",
    dataset_version_id: MOCK_VERSION_ID,
    training_strategy: { training_method: "embedding-ft", epochs: 3 },
    code_version: "rustenwer@d4e5f6",
    template_version: "trainer@1.1.0",
    seed: 7,
    base_model: "tiny-encoder-v1",
    lineage_locked: true,
    created_at: "2026-09-26T11:04:12Z",
  },
];

export const MOCK_INTELLIGENCES: Intelligence[] = [
  {
    id: MOCK_INTELLIGENCE_ID,
    project_id: "11111111-1111-1111-1111-111111111111",
    name: "search-termination",
    description:
      "Executable cognitive system that stops an autonomous search at the right time.",
    primitive: "termination",
    created_at: "2026-09-26T12:10:00Z",
  },
];

export const MOCK_INTELLIGENCE_VERSIONS: IntelligenceVersion[] = [
  {
    id: "iv1iv1iv-iv1i-iv1i-iv1i-iv1iv1iv1iv1",
    intelligence_id: MOCK_INTELLIGENCE_ID,
    version: 1,
    components: {
      models: [{ name: "termination-embedding-classifier", version: 1 }],
      baselines: ["deterministic_rule"],
      harness: "decision-harness@0.9.0",
    },
    notes: "First packaged intelligence: v1 model behind the decision harness.",
    best_evaluation_run_id: null,
    status: "ACTIVE",
    created_at: "2026-09-26T12:12:00Z",
  },
  {
    id: "iv2iv2iv-iv2i-iv2i-iv2i-iv2iv2iv2iv2",
    intelligence_id: MOCK_INTELLIGENCE_ID,
    version: 2,
    components: {
      models: [{ name: "termination-embedding-classifier", version: 2 }],
      baselines: ["deterministic_rule", "keyword_heuristic"],
      harness: "decision-harness@1.0.0",
    },
    notes:
      "v2 model (95.8% on the termination benchmark) with the hardened harness.",
    best_evaluation_run_id: MOCK_EVAL_RUN_DONE_ID,
    status: "ACTIVE",
    created_at: "2026-09-26T12:40:00Z",
  },
];

export const MOCK_USAGE_ROLLUPS: UsageRollups = {
  project_id: "11111111-1111-1111-1111-111111111111",
  total_cost_usd: 18.775,
  by_scope: {
    training_job: {
      scope: "training_job",
      total_cost_usd: 12.4,
      by_kind: { training: 12.4 },
      event_count: 7,
    },
    evaluation: {
      scope: "evaluation",
      total_cost_usd: 5.125,
      by_kind: { evaluation: 5.125 },
      event_count: 3,
    },
    model: {
      scope: "model",
      total_cost_usd: 1.25,
      by_kind: { storage: 1.25 },
      event_count: 2,
    },
  },
  by_kind: { training: 12.4, evaluation: 5.125, storage: 1.25 },
  event_count: 12,
};
