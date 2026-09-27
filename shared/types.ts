/**
 * Rustenwer shared domain types — single source of truth for the web client.
 *
 * Contract: this file is hand-synced with `shared/domain.py` (Python).
 * Any change here MUST be mirrored there and noted in `shared/README.md`.
 * Source of truth for the shapes: product plan §7 (IntelligenceSpec),
 * §2.3 (IntelligencePrimitive), §17 (Candidate lifecycle), §42 (Job lifecycle).
 */

/** Intelligence Primitive — reusable cognitive operation categories (§2.3). */
export type IntelligencePrimitive =
  | 'decision'
  | 'classification'
  | 'ranking'
  | 'filtering'
  | 'search'
  | 'retrieval'
  | 'routing'
  | 'verification'
  | 'critique'
  | 'prediction'
  | 'anomaly_detection'
  | 'diagnosis'
  | 'planning'
  | 'optimization'
  | 'compression'
  | 'memory_selection'
  | 'iteration_control'
  | 'termination'
  | 'exploration'
  | 'selection';

export const INTELLIGENCE_PRIMITIVES: readonly IntelligencePrimitive[] = [
  'decision', 'classification', 'ranking', 'filtering', 'search',
  'retrieval', 'routing', 'verification', 'critique', 'prediction',
  'anomaly_detection', 'diagnosis', 'planning', 'optimization',
  'compression', 'memory_selection', 'iteration_control', 'termination',
  'exploration', 'selection',
] as const;

/** Candidate lifecycle (§17). */
export type CandidateLifecycle =
  | 'PROPOSED'
  | 'VALIDATED'
  | 'TRAINING'
  | 'EVALUATING'
  | 'PASSED'
  | 'FAILED'
  | 'COMPARED'
  | 'PROMOTED'
  | 'REJECTED';

/** Expensive-operation job lifecycle (§42). */
export type JobStatus =
  | 'CREATED'
  | 'QUEUED'
  | 'RUNNING'
  | 'PAUSED'
  | 'FAILED'
  | 'CANCELLED'
  | 'COMPLETED';

/** Project lifecycle (Phase 0; extended in later phases). */
export type ProjectStatus = 'ACTIVE' | 'PAUSED' | 'ARCHIVED';

/** IntelligenceSpec lifecycle status. */
export type IntelligenceSpecStatus = 'DRAFT' | 'DIAGNOSED' | 'APPROVED' | 'ARCHIVED';

/** Evaluation lifecycle status. */
export type EvaluationStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

/** Deployment lifecycle status. */
export type DeploymentStatus = 'DRAFT' | 'ACTIVE' | 'PAUSED' | 'ARCHIVED';

/** Dataset storage format. */
export type DatasetFormat = 'jsonl' | 'csv' | 'inline';

/** Usage accounting scope (§45). */
export type UsageScope =
  | 'project'
  | 'experiment'
  | 'candidate'
  | 'training_job'
  | 'model'
  | 'deployment'
  | 'inference';

/** Usage accounting kind (§45). */
export type UsageKind = 'training' | 'inference' | 'evaluation' | 'storage';

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface ApiUser {
  id: string;
  organization_id: string;
  email: string;
  display_name: string | null;
  role: 'owner' | 'admin' | 'member';
  created_at: string;
}

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** Intelligence Specification — the contract everything downstream operates against (§7). */
export interface IntelligenceSpec {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  problem_statement: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  intelligence_primitive: IntelligencePrimitive;
  quality_requirements: Record<string, unknown> | null;
  latency_requirements: { latency_budget_ms: number | null } | null;
  cost_requirements: Record<string, unknown> | null;
  memory_requirements: Record<string, unknown> | null;
  reliability_requirements: Record<string, unknown> | null;
  constraints: string[];
  available_data: string | null;
  evaluation_definition: string | null;
  deployment_requirements: Record<string, unknown> | null;
  human_review_policy: string | null;
  status: IntelligenceSpecStatus;
  version: number;
}

// ---------------------------------------------------------------------------
// Phase 1 — MVP core entities (plan §41, §61 Phase 1)
// ---------------------------------------------------------------------------

/** Dataset — a named collection of labeled examples owned by a project. */
export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  format: DatasetFormat;
  row_count: number;
  created_at: string;
  updated_at: string;
}

/** DatasetVersion — immutable snapshot of dataset rows + computed stats. */
export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version: number;
  /** Column schema: column -> inferred type name. */
  column_schema: Record<string, string>;
  /** Split fractions, e.g. {train: 0.7, validation: 0.15, test: 0.15}. */
  split_config: { train: number; validation: number; test: number };
  /** Deterministic validation report computed at version creation. */
  stats: DatasetReport;
  created_at: string;
}

/** Deterministic dataset validation report (Dataset Agent, §14). */
export interface DatasetReport {
  dataset_id: string;
  version: number;
  row_count: number;
  column_schema: Record<string, string>;
  /** Label value -> count; null when no label column was declared. */
  class_balance: Record<string, number> | null;
  /** Column -> number of missing values. */
  missing_values: Record<string, number>;
  leakage_flags: string[];
  imbalance_detected: boolean;
  recommended_split: { train: number; validation: number; test: number };
  ready_for_training: boolean;
  notes: string[];
}

/** Result of the Specification/Diagnostic Agent (§8). */
export interface DiagnosisResult {
  spec_id: string;
  /** Rule 13: the platform may conclude no ML is required. */
  ml_necessary: boolean;
  primitive: IntelligencePrimitive;
  /** Condensed answers to the 10 diagnostic questions (§8). */
  rationale: string;
  candidate_approaches: string[];
  data_requirements: string[];
  success_metrics: string[];
  key_constraints: string[];
  diagnosed_at: string;
}

/** One cheap baseline measurement (Baseline-first principle, §16). */
export interface BaselineMetrics {
  /** 'majority_class' | 'keyword_heuristic' | 'deterministic_rule' */
  name: string;
  description: string;
  accuracy: number | null;
  latency_ms_p50: number;
  cost_usd_per_1k: number;
  size_bytes: number;
  predictions_evaluated: number;
}

/** Bar every trained candidate must beat (Rule 9). */
export interface QualityBar {
  accuracy: number;
  latency_ms_p50: number;
  cost_usd_per_1k: number;
}

/** Baseline comparison report produced before any training is proposed. */
export interface BaselineReport {
  spec_id: string;
  dataset_version_id: string;
  baselines: BaselineMetrics[];
  best_baseline: string;
  bar_to_beat: QualityBar;
  evaluated_at: string;
}

/** Training strategy decided by the Training Strategy Agent (§12).
 *  The agent DECIDES; the executor (Phase 2) executes (Rule 3). */
export interface TrainingStrategy {
  /** Null when the strategy is "no training" (Rule 2/13). */
  model_family: string | null;
  /** Structured architecture description (e.g. {type: 'text-classifier', ...}). */
  architecture: Record<string, unknown> | null;
  /** e.g. 'none-deterministic' | 'lora' | 'qlora' | 'distillation' | 'embedding-ft' */
  training_method: string | null;
  objective: string;
  dataset_ref: { dataset_id: string; version: number } | null;
  hyperparameters: Record<string, unknown>;
  evaluation_plan: string;
  compute_budget: { max_gpu_hours: number | null; max_cost_usd: number | null };
  baseline_bar: QualityBar | null;
  rationale: string;
  /** Set when ml_necessary === false: why no training is the right call. */
  no_training_justification: string | null;
}

/** Training Job — expensive operation with an explicit lifecycle (§42).
 *  Real GPU execution lands in Phase 2; Phase 1 records strategy + state. */
export interface TrainingJob {
  id: string;
  project_id: string;
  spec_id: string | null;
  dataset_version_id: string | null;
  name: string;
  status: JobStatus;
  strategy: TrainingStrategy | null;
  compute_budget: { max_gpu_hours: number | null; max_cost_usd: number | null } | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

/** Training Run — one execution attempt of a job. */
export interface TrainingRun {
  id: string;
  job_id: string;
  attempt: number;
  status: JobStatus;
  /** 'local' | 'digitalocean' — the ComputeProvider that ran it. */
  provider: string;
  metrics: Record<string, unknown>;
  artifacts: Record<string, unknown>;
  logs: string | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/** One atomic training checkpoint (Phase 2). */
export interface CheckpointInfo {
  /** e.g. 'ckpt-0003' */
  id: string;
  epoch: number;
  step: number;
  bytes: number;
  created_at: string;
}

/** One immutable, versioned artifact (plan §43). */
export interface ArtifactRecord {
  name: string;
  version: number;
  sha256: string;
  bytes: number;
  created_at: string;
}

/** One point of a metric time series. */
export interface MetricPoint {
  step: number;
  value: number;
  ts: string;
}

/** A named metric time series (loss, lr, grad_norm, …). */
export interface MetricSeries {
  name: string;
  points: MetricPoint[];
}

/** All metric series of a run. */
export interface RunMetrics {
  run_id: string;
  series: MetricSeries[];
  latest: Record<string, number>;
}

/** Wall-time cost accounting for one run (plan §45). */
export interface RunCost {
  run_id: string;
  provider: string;
  seconds: number;
  usd: number;
  rate_usd_per_hour: number;
}

/** Model — a learned computational model (plan §2.1). */
export interface Model {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_at: string;
}

/** ModelVersion — immutable version of a model (§43). */
export interface ModelVersion {
  id: string;
  model_id: string;
  version: number;
  training_run_id: string | null;
  architecture: Record<string, unknown> | null;
  size_bytes: number | null;
  metrics: Record<string, unknown>;
  artifact_uri: string | null;
  created_at: string;
}

/** Evaluation — task-specific measurement of a candidate or baseline (§15).
 *  The evaluator is independent of the training mechanism (Rule 11). */
export interface Evaluation {
  id: string;
  project_id: string;
  spec_id: string;
  dataset_version_id: string;
  name: string;
  status: EvaluationStatus;
  results: EvaluationResults | null;
  created_at: string;
  completed_at: string | null;
}

export interface EvaluationResults {
  baselines: BaselineMetrics[];
  bar_to_beat: QualityBar;
  recommendation: string;
  evaluated_at: string;
}

/** Deployment — an approved Intelligence/Model served as an API endpoint. */
export interface Deployment {
  id: string;
  project_id: string;
  spec_id: string;
  model_version_id: string | null;
  name: string;
  status: DeploymentStatus;
  endpoint_url: string | null;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** UsageEvent — one cost/usage record (§45). */
export interface UsageEvent {
  id: string;
  project_id: string;
  scope: UsageScope;
  scope_id: string;
  kind: UsageKind;
  quantity: number;
  unit: string;
  cost_usd: number;
  recorded_at: string;
}

/** Aggregated cost view for a project (§45). */
export interface UsageSummary {
  project_id: string;
  total_cost_usd: number;
  by_scope: Record<string, number>;
  by_kind: Record<string, number>;
  event_count: number;
}

/** Job status transition request (§42). */
export interface JobTransition {
  to: JobStatus;
}
