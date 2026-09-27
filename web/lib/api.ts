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
  Dataset,
  DatasetReport,
  DatasetVersion,
  Deployment,
  DeploymentStatus,
  DiagnosisResult,
  Evaluation,
  IntelligencePrimitive,
  IntelligenceSpec,
  JobStatus,
  Model,
  ModelVersion,
  Project,
  ProjectStatus,
  TrainingJob,
  TrainingRun,
  TrainingStrategy,
  UsageEvent,
  UsageKind,
  UsageScope,
  UsageSummary,
} from "../../shared/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Phase 0 stub auth: any well-formed Bearer token is accepted by the API. */
const DEV_TOKEN = "phase0-dev-token";

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
