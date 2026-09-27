/**
 * Phase 5 — Training Method Knowledge clients (plan §11, §3, §52).
 *
 * Domain types are imported from the single source of truth
 * (`shared/types.ts`) with `import type`, which is erased at build time —
 * no bundler path issues (same pattern as web/lib/api.ts).
 *
 * Contract mirror of `shared/README.md`. The Phase 5 API routes live in
 * `api/app/methods/` (built in parallel by the backend agent); the shapes
 * below follow the Phase 5 plan §6 verbatim and are documented inline so
 * the coordinator can verify backend compatibility.
 */

import type {
  BaselineReport,
  DiagnosisResult,
  Evaluation,
  IntelligenceSpec,
  MethodCategory,
  MethodRecommendation,
  MethodValidationStatus,
  ResearchFinding,
  TrainingMethod,
} from "../../shared/types";
import { DEV_TOKEN } from "./api";

/** Re-exported so consumers can import everything Phase 5 from this module. */
export type {
  MethodCategory,
  MethodRank,
  MethodRecommendation,
  MethodValidationStatus,
  MethodVeto,
  ResearchFinding,
  TrainingMethod,
} from "../../shared/types";

/** The §10 taxonomy as an ordered category tree (from shared/types.ts). */
export { METHOD_CATEGORIES } from "../../shared/types";

/** Payload for POST /api/v1/methods/recommend (plan §6). */
export interface RecommendMethodsInput {
  spec: IntelligenceSpec;
  diagnosis: DiagnosisResult | null;
  baseline_report?: BaselineReport | null;
  allow_generic?: boolean;
}

// ---------------------------------------------------------------------------
// API shapes coded against (Phase 5 plan §6 — verify backend compatibility)
// ---------------------------------------------------------------------------
//
// GET  /api/v1/methods?category=&status=  → TrainingMethod[] (bare array,
//                                          like every other list endpoint)
// GET  /api/v1/methods/{slug}            → { slug, versions: TrainingMethod[],
//                                            current: TrainingMethod }
//                                          (client also accepts a bare
//                                          TrainingMethod[] and derives
//                                          current = highest version)
// POST /api/v1/methods/recommend         → body RecommendMethodsInput,
//                                          returns MethodRecommendation
// GET  /api/v1/research                  → ResearchFinding[] (bare array)
//

/** GET /api/v1/methods/{slug} response envelope (plan: "all versions + current"). */
export interface MethodDetailResponse {
  slug: string;
  versions: TrainingMethod[];
  current: TrainingMethod;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const REQUEST_TIMEOUT_MS = 8000;

export class MethodsApiOfflineError extends Error {
  constructor(message = "API unreachable") {
    super(message);
    this.name = "MethodsApiOfflineError";
  }
}

class MethodsApiError extends Error {
  readonly status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "MethodsApiError";
    this.status = status;
  }
}

async function methodsRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
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
      throw new MethodsApiError(res.status, detail);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof MethodsApiError) throw err;
    throw new MethodsApiOfflineError(
      `Could not reach ${API_BASE_URL}${path}: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    clearTimeout(timeout);
  }
}

/** True when the methods API cannot be reached (mirrors api.ts semantics). */
export function isMethodsApiOfflineError(
  err: unknown,
): err is MethodsApiOfflineError {
  return err instanceof MethodsApiOfflineError;
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

/** List methods, optionally filtered by category and/or validation status. */
export async function listMethods(input?: {
  category?: MethodCategory | string;
  status?: MethodValidationStatus | string;
}): Promise<TrainingMethod[]> {
  const params = new URLSearchParams();
  if (input?.category) params.set("category", input.category);
  if (input?.status) params.set("status", input.status);
  const qs = params.toString();
  return methodsRequest<TrainingMethod[]>(
    `/api/v1/methods${qs ? `?${qs}` : ""}`,
  );
}

/**
 * Normalize the GET /api/v1/methods/{slug} response: accepts the documented
 * envelope {slug, versions, current} AND a bare TrainingMethod[] (current =
 * highest version) so a simpler backend shape still works.
 */
export function normalizeMethodDetailResponse(
  raw: MethodDetailResponse | TrainingMethod[],
): MethodDetailResponse {
  if (Array.isArray(raw)) {
    const versions = [...raw].sort((a, b) => a.version - b.version);
    const current = versions[versions.length - 1];
    if (!current) {
      throw new MethodsApiError(404, "No method versions returned.");
    }
    return { slug: current.slug, versions, current };
  }
  return raw;
}

/** All versions of one method plus the current one. */
export async function getMethodDetail(
  slug: string,
): Promise<MethodDetailResponse> {
  const raw = await methodsRequest<MethodDetailResponse | TrainingMethod[]>(
    `/api/v1/methods/${encodeURIComponent(slug)}`,
  );
  return normalizeMethodDetailResponse(raw);
}

/**
 * Ranked + vetoed training methods for a spec (plan §3).
 * `diagnosis` may be null (no diagnosis yet); `baseline_report` is derived
 * from the most recent completed evaluation when available.
 */
export async function recommendMethods(
  input: RecommendMethodsInput,
): Promise<MethodRecommendation> {
  return methodsRequest<MethodRecommendation>("/api/v1/methods/recommend", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** Research knowledge entries (plan §52). */
export async function listResearchFindings(): Promise<ResearchFinding[]> {
  return methodsRequest<ResearchFinding[]>("/api/v1/research");
}

// ---------------------------------------------------------------------------
// Pure helpers (unit-checkable without a backend)
// ---------------------------------------------------------------------------

/** Citation string the Strategy Agent embeds (plan §3): "lora@1". */
export function methodCitation(method: TrainingMethod): string {
  return `${method.slug}@${method.version}`;
}

/** Human label for a taxonomy category (§10). */
export function methodCategoryLabel(category: MethodCategory | string): string {
  const labels: Record<string, string> = {
    supervised: "Supervised",
    peft: "Parameter-efficient (PEFT)",
    self_supervised: "Self-supervised",
    preference_optimization: "Preference optimization",
    reinforcement_learning: "Reinforcement learning",
    distillation: "Distillation",
    contrastive: "Contrastive",
    synthetic_data: "Synthetic data",
    curriculum: "Curriculum",
    search_evolutionary: "Search & evolutionary",
    hybrid: "Hybrid",
  };
  return labels[category] ?? category.replace(/_/g, " ");
}

/**
 * Build a BaselineReport from the most recent completed Evaluation so the
 * recommend endpoint gets the real baseline bar (Rule 9) instead of nothing.
 * Returns null when no usable evaluation exists.
 */
export function baselineReportFromEvaluation(
  specId: string,
  evaluation: Evaluation | undefined,
): BaselineReport | null {
  const results = evaluation?.results;
  if (!results || results.baselines.length === 0) return null;
  const best = results.baselines.reduce((a, b) =>
    (b.accuracy ?? -1) > (a.accuracy ?? -1) ? b : a,
  );
  return {
    spec_id: specId,
    dataset_version_id: evaluation?.dataset_version_id ?? "",
    baselines: results.baselines,
    best_baseline: best.name,
    bar_to_beat: results.bar_to_beat,
    evaluated_at: results.evaluated_at,
  };
}

// ---------------------------------------------------------------------------
// Mock fallback dataset (Phase 5 demo only).
// Served ONLY when the API is unreachable; the UI labels it as mock data.
// Consistent with the Phase 5 seeding contract: 5 VALIDATED methods
// (classifier, lora, qlora, distillation, contrastive — the last two new in
// Phase 5 with real CPU adapters) + 8 KNOWN taxonomy entries with no adapter.
// ---------------------------------------------------------------------------

const MOCK_METHODS_BASE: {
  version: number;
  evaluation_requirements: string[];
  notes: string;
} = {
  version: 1,
  evaluation_requirements: ["beat the baseline bar (Rule 9)"],
  notes: "MOCK entry — served offline for demo purposes.",
};

export const MOCK_METHODS: TrainingMethod[] = [
  {
    slug: "classifier",
    name: "Supervised classifier",
    category: "supervised",
    status: "VALIDATED",
    supported_tasks: ["classification", "termination", "filtering", "routing"],
    data_requirements: { min_rows: 10, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 0,
    },
    strengths: [
      "Trains in seconds on CPU; deterministic MLP implementation.",
      "Strong default when the spec is small and labeled.",
    ],
    weaknesses: ["Needs labeled rows for every class of interest."],
    failure_modes: [
      "Collapses to the majority class on imbalanced data — check the DatasetReport first.",
    ],
    compatible_architectures: ["embedding-classifier", "mlp"],
    compatible_objectives: ["maximize accuracy under a latency budget"],
    implementation_templates: ["classifier"],
    locally_runnable: true,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "lora",
    name: "LoRA fine-tuning",
    category: "peft",
    status: "VALIDATED",
    supported_tasks: ["classification", "ranking", "verification", "critique"],
    data_requirements: { min_rows: 50, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 0.76,
    },
    strengths: [
      "600 trainable params adapt a frozen backbone cheaply (Phase 2 proved it on CPU).",
      "Kaiming-uniform A / zero B init trick keeps early updates stable.",
    ],
    weaknesses: [
      "Needs a pretrained backbone; not a from-scratch learner.",
      "Rank too high overfits tiny datasets.",
    ],
    failure_modes: [
      "Silent degradation when the base model's domain mismatches the spec's inputs.",
    ],
    compatible_architectures: ["encoder-adapter", "transformer"],
    compatible_objectives: ["adapt a backbone under a cost budget"],
    implementation_templates: ["lora"],
    locally_runnable: true,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "qlora",
    name: "QLoRA fine-tuning",
    category: "peft",
    status: "VALIDATED",
    supported_tasks: ["classification", "ranking", "verification", "critique"],
    data_requirements: { min_rows: 50, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: true,
      min_vram_gb: 8,
      rough_cost_per_hour_usd: 0.76,
    },
    strengths: [
      "4-bit base weights: ~75% memory saving vs LoRA at comparable quality.",
    ],
    weaknesses: [
      "CUDA-only — no local CPU path; requires the digitalocean provider.",
    ],
    failure_modes: [
      "Quantization drift on very long contexts; revalidate calibration after training.",
    ],
    compatible_architectures: ["encoder-adapter", "transformer"],
    compatible_objectives: ["adapt a large backbone on a single GPU"],
    implementation_templates: ["qlora"],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "distillation",
    name: "Knowledge distillation",
    category: "distillation",
    status: "VALIDATED",
    supported_tasks: ["classification", "termination", "filtering"],
    data_requirements: { min_rows: 20, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 0,
    },
    strengths: [
      "Temperature-scaled soft targets let a small student match its teacher closely.",
      "Proven on CPU in Phase 5: distilled student ≥ from-scratch student.",
    ],
    weaknesses: [
      "Trains two models (teacher + student): double the training cost.",
    ],
    failure_modes: [
      "A bad teacher distills bad habits — validate the teacher against the baseline bar first.",
    ],
    compatible_architectures: ["mlp", "embedding-classifier"],
    compatible_objectives: ["shrink a good model to a tiny deployable one"],
    implementation_templates: ["distillation"],
    locally_runnable: true,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "contrastive",
    name: "Contrastive embeddings",
    category: "contrastive",
    status: "VALIDATED",
    supported_tasks: ["ranking", "retrieval", "similarity"],
    data_requirements: { min_rows: 30, labeled: true, pairwise: true },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 0,
    },
    strengths: [
      "InfoNCE-style loss over same-class pairs; nearest-centroid retrieval on CPU.",
      "Natural fit for ranking / retrieval / similarity primitives.",
    ],
    weaknesses: [
      "Needs meaningful positive pairs; garbage pairs produce garbage embeddings.",
    ],
    failure_modes: [
      "Representation collapse — all embeddings converge to one point — when the temperature is mis-set.",
    ],
    compatible_architectures: ["embedding-tower"],
    compatible_objectives: ["maximize retrieval accuracy at near-zero cost"],
    implementation_templates: ["contrastive"],
    locally_runnable: true,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "instruction-tuning",
    name: "Instruction tuning",
    category: "supervised",
    status: "KNOWN",
    supported_tasks: ["critique", "verification", "planning"],
    data_requirements: { min_rows: 1000, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: true,
      min_vram_gb: 16,
      rough_cost_per_hour_usd: 2.5,
    },
    strengths: ["Aligns a base model to follow task instructions reliably."],
    weaknesses: ["Needs a large instruction-following dataset we do not have."],
    failure_modes: ["Instruction drift: the model answers the wrong task."],
    compatible_architectures: ["decoder-only-llm"],
    compatible_objectives: ["improve instruction following"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "dpo",
    name: "Direct Preference Optimization",
    category: "preference_optimization",
    status: "KNOWN",
    supported_tasks: ["critique", "ranking", "verification"],
    data_requirements: { min_rows: 500, labeled: true, pairwise: true },
    compute_requirements: {
      gpu_required: true,
      min_vram_gb: 16,
      rough_cost_per_hour_usd: 2.5,
    },
    strengths: [
      "No reward model needed; learns directly from preferred/rejected pairs.",
    ],
    weaknesses: ["Preference pairs are expensive to collect for our specs."],
    failure_modes: [
      "Over-optimization on noisy preferences flips the intended behavior.",
    ],
    compatible_architectures: ["decoder-only-llm"],
    compatible_objectives: ["align outputs to human preference"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "rl-verifiable",
    name: "RL with verifiable rewards",
    category: "reinforcement_learning",
    status: "KNOWN",
    supported_tasks: ["planning", "optimization", "iteration_control"],
    data_requirements: { min_rows: 100, labeled: false, pairwise: false },
    compute_requirements: {
      gpu_required: true,
      min_vram_gb: 24,
      rough_cost_per_hour_usd: 4.47,
    },
    strengths: [
      "Learns from a verifier instead of labels — works where labeling is impossible.",
    ],
    weaknesses: [
      "Needs a trustworthy verifier; training is unstable without one.",
    ],
    failure_modes: ["Reward hacking: the policy games the verifier."],
    compatible_architectures: ["policy-network"],
    compatible_objectives: ["optimize a verifiable outcome"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "self-supervised",
    name: "Self-supervised pretraining",
    category: "self_supervised",
    status: "KNOWN",
    supported_tasks: ["anomaly_detection", "compression", "memory_selection"],
    data_requirements: { min_rows: 10000, labeled: false, pairwise: false },
    compute_requirements: {
      gpu_required: true,
      min_vram_gb: 24,
      rough_cost_per_hour_usd: 4.47,
    },
    strengths: ["Learns structure from raw, unlabeled data at scale."],
    weaknesses: ["Data appetite far exceeds our spec-scale datasets."],
    failure_modes: [
      "Pretraining on irrelevant data transfers nothing to the target task.",
    ],
    compatible_architectures: ["masked-encoder", "autoregressive"],
    compatible_objectives: ["learn representations from unlabeled data"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "synthetic-data",
    name: "Synthetic data training",
    category: "synthetic_data",
    status: "KNOWN",
    supported_tasks: ["classification", "termination"],
    data_requirements: { min_rows: 100, labeled: false, pairwise: false },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 0.1,
    },
    strengths: [
      "Bootstraps training when real labels are scarce (our blob fixtures are the toy version).",
    ],
    weaknesses: ["The synthetic distribution may not match production."],
    failure_modes: [
      "Sim-to-real gap: great on synthetic, mediocre on real rows.",
    ],
    compatible_architectures: ["mlp", "embedding-classifier"],
    compatible_objectives: ["learn with scarce labels"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "curriculum",
    name: "Curriculum learning",
    category: "curriculum",
    status: "KNOWN",
    supported_tasks: ["classification", "planning"],
    data_requirements: { min_rows: 200, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 0.1,
    },
    strengths: ["Easy-to-hard ordering can stabilize small-data training."],
    weaknesses: ["Needs a difficulty signal, which is itself a modeling task."],
    failure_modes: ["A bad difficulty ranking is worse than random order."],
    compatible_architectures: ["mlp"],
    compatible_objectives: ["stabilize training on limited data"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "evolutionary-search",
    name: "Evolutionary search",
    category: "search_evolutionary",
    status: "KNOWN",
    supported_tasks: ["classification", "planning"],
    data_requirements: { min_rows: 200, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 1.0,
    },
    strengths: ["Gradient-free; searches architectures and hyperparameters."],
    weaknesses: ["Evaluates many candidates — expensive in wall-clock time."],
    failure_modes: [
      "Converges to local optima on deceptive fitness landscapes.",
    ],
    compatible_architectures: ["any"],
    compatible_objectives: ["search a discrete design space"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
  {
    slug: "embedding-ft",
    name: "Embedding fine-tuning",
    category: "supervised",
    status: "KNOWN",
    supported_tasks: ["classification", "termination"],
    data_requirements: { min_rows: 10, labeled: true, pairwise: false },
    compute_requirements: {
      gpu_required: false,
      min_vram_gb: null,
      rough_cost_per_hour_usd: 0,
    },
    strengths: ["Fast adapter for tiny labeled sets; the Phase 1–2 default."],
    weaknesses: ["No local adapter registered yet — KNOWN, not VALIDATED."],
    failure_modes: ["Overfits single-digit datasets without held-out checks."],
    compatible_architectures: ["embedding-classifier"],
    compatible_objectives: ["adapt quickly on tiny labeled data"],
    implementation_templates: [],
    locally_runnable: false,
    ...MOCK_METHODS_BASE,
  },
];

/**
 * Mock recommendation for the termination spec (MOCK_SPECS[0]):
 * classifier / lora / distillation ranked, qlora vetoed (no CUDA),
 * embedding-ft vetoed (no adapter), contrastive vetoed (wrong primitive).
 */
export const MOCK_METHOD_RECOMMENDATION: MethodRecommendation = {
  recommended: [
    {
      slug: "distillation",
      version: 1,
      score: 0.91,
      reasons: [
        "The 12 labeled rows fit distillation's data requirements (min 20 rows — near threshold, seeded blob path covers it).",
        "Locally runnable on CPU; no GPU needed.",
        "Student matches the teacher closely while staying deployable inside the 50ms budget.",
      ],
    },
    {
      slug: "classifier",
      version: 1,
      score: 0.87,
      reasons: [
        "Termination is a supported task; the MLP trains in seconds on CPU.",
        "Cheapest option: zero training cost, zero GPU.",
      ],
    },
    {
      slug: "lora",
      version: 1,
      score: 0.72,
      reasons: [
        "Compatible with the classification objective and proven on CPU (Phase 2).",
        "Ranked below distillation because it needs a pretrained backbone the spec does not have.",
      ],
    },
  ],
  vetoed: [
    {
      slug: "qlora",
      version: 1,
      reason: "No CUDA here; use the digitalocean provider.",
    },
    {
      slug: "embedding-ft",
      version: 1,
      reason: "No local adapter registered yet.",
    },
    {
      slug: "contrastive",
      version: 1,
      reason:
        "Only recommended for ranking/retrieval/similarity primitives — termination is none of those (pass allow_generic to reconsider).",
    },
  ],
  citations: ["distillation@1", "classifier@1", "lora@1"],
  note: "",
};

/** Seeded research knowledge (plan §4). */
export const MOCK_RESEARCH_FINDINGS: ResearchFinding[] = [
  {
    technique: "LoRA initialization trick",
    useful_for: ["parameter-efficient fine-tuning of classifiers"],
    requires: ["frozen pretrained backbone", "rank r", "labeled data"],
    advantage:
      "Kaiming-uniform A with zero B keeps the adapter near-identity at start; early training updates stay stable (matches our LoRAAdapter).",
    weakness: "Poor init on A can stall the first epochs on tiny datasets.",
    source: "validated: phase-2 e2e",
    version: 1,
  },
  {
    technique: "QLoRA 4-bit quantization",
    useful_for: ["fine-tuning large models on a single GPU"],
    requires: ["CUDA GPU", "4-bit base weights", "quantization kernels"],
    advantage: "~75% memory saving vs LoRA at comparable downstream quality.",
    weakness:
      "CUDA-only; quantization drift can hurt calibration on long contexts.",
    source: "validated: phase-2 e2e",
    version: 1,
  },
  {
    technique: "Distillation with temperature-scaled soft targets",
    useful_for: ["compressing a strong teacher into a tiny deployable student"],
    requires: ["trained teacher", "labeled data", "temperature τ > 1"],
    advantage:
      "The student matches the teacher closely and beats from-scratch training on the same data.",
    weakness: "Trains two models; a bad teacher distills bad habits.",
    source: "validated: phase-5 e2e",
    version: 1,
  },
  {
    technique: "Contrastive embeddings for ranking/similarity",
    useful_for: ["retrieval primitives", "ranking primitives"],
    requires: ["meaningful positive/negative pairs", "temperature setting"],
    advantage:
      "InfoNCE-style loss produces nearest-centroid retrieval that runs on CPU at near-zero cost.",
    weakness: "Representation collapse when the temperature is mis-set.",
    source: "validated: phase-5 e2e",
    version: 1,
  },
];
