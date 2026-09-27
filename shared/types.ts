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
