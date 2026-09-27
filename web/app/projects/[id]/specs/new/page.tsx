"use client";

import { ArrowLeft, ArrowRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import {
  INTELLIGENCE_PRIMITIVES,
  type IntelligencePrimitive,
} from "../../../../../../shared/types";
import {
  type CreateSpecInput,
  createSpec,
  isApiOfflineError,
} from "../../../../../lib/api";

export const dynamic = "force-dynamic";

const STEPS = ["Describe", "Inputs & outputs", "Review"] as const;

const INPUT_STYLE =
  "block w-full min-h-[44px] rounded-lg border border-line bg-paper px-3.5 py-2.5 text-base text-charcoal placeholder:text-muted-ink/70 transition-colors duration-200 focus:border-charcoal";

function prettyLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function parseJsonObject(
  raw: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  const trimmed = raw.trim();
  if (trimmed === "") return { ok: true, value: {} };
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      return {
        ok: false,
        error: 'Must be a JSON object, e.g. {"key": "value"}.',
      };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch (err) {
    return {
      ok: false,
      error: `Invalid JSON: ${err instanceof Error ? err.message : "parse error"}.`,
    };
  }
}

/**
 * 3-step Intelligence Spec wizard. Plain-language helper text on purpose:
 * describe the behavior you want, not ML terms — Rustenwer decides how to
 * build it. "Auto-detect" leaves the primitive to the Diagnostic Agent.
 */
export default function NewSpecPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [problem, setProblem] = useState("");
  const [description, setDescription] = useState("");
  const [primitive, setPrimitive] = useState<string>("");
  const [inputSchema, setInputSchema] = useState("");
  const [outputSchema, setOutputSchema] = useState("");
  const [latencyBudget, setLatencyBudget] = useState("");
  const [quality, setQuality] = useState("");
  const [cost, setCost] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function validateStep(next: number): boolean {
    setError(null);
    if (next === 1 || next === 2) {
      if (name.trim().length < 3) {
        setError("Give the spec a name of at least 3 characters.");
        return false;
      }
      if (problem.trim().length < 20) {
        setError(
          "Describe the problem in at least 20 characters — say what should happen.",
        );
        return false;
      }
    }
    if (next === 2) {
      for (const [label, raw] of [
        ["Input schema", inputSchema],
        ["Output schema", outputSchema],
        ["Quality requirements", quality],
        ["Cost requirements", cost],
      ] as const) {
        const parsed = parseJsonObject(raw);
        if (!parsed.ok) {
          setError(`${label}: ${parsed.error}`);
          return false;
        }
      }
      if (latencyBudget.trim() !== "") {
        const n = Number(latencyBudget);
        if (!Number.isFinite(n) || n < 0) {
          setError(
            "Latency budget must be a non-negative number of milliseconds.",
          );
          return false;
        }
      }
    }
    return true;
  }

  function goTo(next: number) {
    if (next > step && !validateStep(next)) return;
    setStep(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleCreate() {
    if (!validateStep(2)) return;
    setPending(true);
    setError(null);

    const parsedInput = parseJsonObject(inputSchema);
    const parsedOutput = parseJsonObject(outputSchema);
    const parsedQuality = parseJsonObject(quality);
    const parsedCost = parseJsonObject(cost);
    if (
      !parsedInput.ok ||
      !parsedOutput.ok ||
      !parsedQuality.ok ||
      !parsedCost.ok
    ) {
      setError("Fix the JSON errors above before creating the spec.");
      setPending(false);
      return;
    }

    const payload: CreateSpecInput = {
      name: name.trim(),
      description: description.trim() || undefined,
      problem_statement: problem.trim(),
      ...(primitive
        ? { intelligence_primitive: primitive as IntelligencePrimitive }
        : {}),
      ...(inputSchema.trim() ? { input_schema: parsedInput.value } : {}),
      ...(outputSchema.trim() ? { output_schema: parsedOutput.value } : {}),
      ...(latencyBudget.trim() !== ""
        ? {
            latency_requirements: {
              latency_budget_ms: Number(latencyBudget),
            },
          }
        : {}),
      ...(quality.trim() ? { quality_requirements: parsedQuality.value } : {}),
      ...(cost.trim() ? { cost_requirements: parsedCost.value } : {}),
    };

    try {
      const spec = await createSpec(projectId, payload);
      router.push(`/projects/${projectId}/specs/${spec.id}`);
    } catch (err) {
      if (isApiOfflineError(err)) {
        setError(
          "The API is offline, so the spec could not be created. Start the backend at http://localhost:8000 and try again.",
        );
      } else {
        setError(err instanceof Error ? err.message : "Failed to create spec.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/projects/${projectId}`}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to project
      </Link>

      <h1 className="mt-4 font-display text-3xl font-bold tracking-tight text-charcoal">
        New Intelligence Spec
      </h1>
      <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
        A spec is the contract everything downstream operates against. Describe
        the behavior you want in plain language — Rustenwer decides the
        smallest, cheapest, fastest intelligence that delivers it.
      </p>

      <ol aria-label="Progress" className="mt-8 flex items-center gap-2">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className="flex flex-1 items-center gap-2 last:flex-none"
          >
            <span
              aria-current={i === step ? "step" : undefined}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold transition-colors duration-200 ${
                i < step
                  ? "bg-charcoal text-platinum"
                  : i === step
                    ? "bg-charcoal text-platinum"
                    : "bg-platinum text-muted-ink"
              }`}
            >
              {i + 1}
            </span>
            <span
              className={`text-sm font-semibold ${i === step ? "text-charcoal" : "text-muted-ink"}`}
            >
              {label}
            </span>
            {i < STEPS.length - 1 && (
              <span className="mx-1 h-px flex-1 bg-line" aria-hidden="true" />
            )}
          </li>
        ))}
      </ol>

      <div className="mt-6 rounded-xl border border-line bg-card p-6 sm:p-8">
        {step === 0 && (
          <div className="space-y-5">
            <div>
              <label
                htmlFor="spec-name"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Spec name <span aria-hidden="true">*</span>
              </label>
              <input
                id="spec-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Search termination intelligence"
                maxLength={200}
                className={INPUT_STYLE}
              />
            </div>
            <div>
              <label
                htmlFor="spec-problem"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                What should happen? <span aria-hidden="true">*</span>
              </label>
              <textarea
                id="spec-problem"
                value={problem}
                onChange={(e) => setProblem(e.target.value)}
                rows={5}
                maxLength={4000}
                placeholder="A search explores the web for useful findings. After each step it should decide whether to keep searching or stop — stopping early misses discoveries, searching too long wastes budget."
                className={INPUT_STYLE}
                aria-describedby="spec-problem-help"
              />
              <p
                id="spec-problem-help"
                className="mt-1.5 text-xs leading-5 text-muted-ink"
              >
                Describe the behavior, not ML terms. What goes in, what comes
                out, and what “good” looks like — no need to mention models,
                training, or algorithms.
              </p>
            </div>
            <div>
              <label
                htmlFor="spec-description"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Short description{" "}
                <span className="font-normal text-muted-ink">(optional)</span>
              </label>
              <textarea
                id="spec-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                maxLength={2000}
                placeholder="One sentence for dashboards and teammates."
                className={INPUT_STYLE}
              />
            </div>
            <div>
              <label
                htmlFor="spec-primitive"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Type of intelligence
              </label>
              <select
                id="spec-primitive"
                value={primitive}
                onChange={(e) => setPrimitive(e.target.value)}
                className={`${INPUT_STYLE} cursor-pointer`}
                aria-describedby="spec-primitive-help"
              >
                <option value="">Auto-detect from the description</option>
                {INTELLIGENCE_PRIMITIVES.map((p) => (
                  <option key={p} value={p}>
                    {prettyLabel(p)}
                  </option>
                ))}
              </select>
              <p
                id="spec-primitive-help"
                className="mt-1.5 text-xs leading-5 text-muted-ink"
              >
                Pick the closest match if you know it; otherwise leave
                auto-detect and the Diagnostic Agent will choose.
              </p>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <div>
              <label
                htmlFor="spec-input-schema"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Inputs{" "}
                <span className="font-normal text-muted-ink">
                  (JSON object, optional)
                </span>
              </label>
              <textarea
                id="spec-input-schema"
                value={inputSchema}
                onChange={(e) => setInputSchema(e.target.value)}
                rows={4}
                spellCheck={false}
                placeholder={'{\n  "search_state": { "type": "object" }\n}'}
                className={`${INPUT_STYLE} font-mono text-sm`}
                aria-describedby="spec-input-help"
              />
              <p
                id="spec-input-help"
                className="mt-1.5 text-xs leading-5 text-muted-ink"
              >
                What information does the intelligence receive? Name each field
                and its type — JSON object format.
              </p>
            </div>
            <div>
              <label
                htmlFor="spec-output-schema"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Outputs{" "}
                <span className="font-normal text-muted-ink">
                  (JSON object, optional)
                </span>
              </label>
              <textarea
                id="spec-output-schema"
                value={outputSchema}
                onChange={(e) => setOutputSchema(e.target.value)}
                rows={4}
                spellCheck={false}
                placeholder={
                  '{\n  "decision": { "enum": ["continue", "stop"] },\n  "confidence": { "type": "number" }\n}'
                }
                className={`${INPUT_STYLE} font-mono text-sm`}
              />
              <p className="mt-1.5 text-xs leading-5 text-muted-ink">
                What must it produce for each input? Describe the shape of the
                answer.
              </p>
            </div>
            <div>
              <label
                htmlFor="spec-latency"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Latency budget (ms){" "}
                <span className="font-normal text-muted-ink">(optional)</span>
              </label>
              <input
                id="spec-latency"
                type="number"
                min={0}
                value={latencyBudget}
                onChange={(e) => setLatencyBudget(e.target.value)}
                placeholder="e.g. 50"
                className={`${INPUT_STYLE} max-w-48`}
              />
              <p className="mt-1.5 text-xs leading-5 text-muted-ink">
                How fast must one answer arrive? Leave empty if speed does not
                matter.
              </p>
            </div>
            <div>
              <label
                htmlFor="spec-quality"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Quality requirements{" "}
                <span className="font-normal text-muted-ink">
                  (JSON object, optional)
                </span>
              </label>
              <textarea
                id="spec-quality"
                value={quality}
                onChange={(e) => setQuality(e.target.value)}
                rows={3}
                spellCheck={false}
                placeholder={
                  '{\n  "objective": "maximize useful discoveries"\n}'
                }
                className={`${INPUT_STYLE} font-mono text-sm`}
              />
            </div>
            <div>
              <label
                htmlFor="spec-cost"
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Cost requirements{" "}
                <span className="font-normal text-muted-ink">
                  (JSON object, optional)
                </span>
              </label>
              <textarea
                id="spec-cost"
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                rows={3}
                spellCheck={false}
                placeholder={'{\n  "max_cost_usd_per_1k_decisions": 0.01\n}'}
                className={`${INPUT_STYLE} font-mono text-sm`}
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <h2 className="font-display text-lg font-bold text-charcoal">
              Review before creating
            </h2>
            <dl className="mt-4 space-y-4 text-sm">
              <div>
                <dt className="font-semibold text-muted-ink">Name</dt>
                <dd className="mt-0.5 text-charcoal">{name.trim()}</dd>
              </div>
              <div>
                <dt className="font-semibold text-muted-ink">
                  What should happen
                </dt>
                <dd className="mt-0.5 leading-6 whitespace-pre-wrap text-charcoal">
                  {problem.trim()}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-muted-ink">
                  Type of intelligence
                </dt>
                <dd className="mt-0.5 text-charcoal">
                  {primitive ? prettyLabel(primitive) : "Auto-detect"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-muted-ink">Latency budget</dt>
                <dd className="mt-0.5 text-charcoal">
                  {latencyBudget.trim() !== ""
                    ? `${latencyBudget} ms`
                    : "Not set"}
                </dd>
              </div>
              {(inputSchema.trim() ||
                outputSchema.trim() ||
                quality.trim() ||
                cost.trim()) && (
                <div>
                  <dt className="font-semibold text-muted-ink">
                    Schemas & requirements
                  </dt>
                  <dd className="mt-0.5 space-y-2">
                    {inputSchema.trim() && (
                      <pre className="overflow-x-auto rounded-lg bg-paper p-3 font-mono text-xs text-charcoal">
                        inputs: {inputSchema.trim()}
                      </pre>
                    )}
                    {outputSchema.trim() && (
                      <pre className="overflow-x-auto rounded-lg bg-paper p-3 font-mono text-xs text-charcoal">
                        outputs: {outputSchema.trim()}
                      </pre>
                    )}
                    {quality.trim() && (
                      <pre className="overflow-x-auto rounded-lg bg-paper p-3 font-mono text-xs text-charcoal">
                        quality: {quality.trim()}
                      </pre>
                    )}
                    {cost.trim() && (
                      <pre className="overflow-x-auto rounded-lg bg-paper p-3 font-mono text-xs text-charcoal">
                        cost: {cost.trim()}
                      </pre>
                    )}
                  </dd>
                </div>
              )}
            </dl>
            <p className="mt-4 text-sm leading-6 text-muted-ink">
              Creating the spec saves it as a draft. The Diagnostic Agent runs
              next — it may even conclude that no ML is needed at all.
            </p>
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="mt-6 rounded-lg bg-[#DC2626]/10 px-3.5 py-2.5 text-sm font-medium text-[#8f1d1d]"
          >
            {error}
          </p>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            disabled={step === 0 || pending}
            onClick={() => goTo(step - 1)}
            className="inline-flex min-h-[44px] cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-paper px-4 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back
          </button>
          {step < 2 ? (
            <button
              type="button"
              onClick={() => goTo(step + 1)}
              className="inline-flex min-h-[44px] cursor-pointer items-center gap-1.5 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft"
            >
              Continue
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              disabled={pending}
              onClick={handleCreate}
              className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {pending ? "Creating…" : "Create spec"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
