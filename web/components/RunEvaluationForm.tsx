"use client";

import { Loader2, Play } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { EvaluationRun, SubjectKind } from "../../shared/types";
import { isApiOfflineError, startEvaluationRun } from "../lib/api";
import {
  BUTTON_PRIMARY,
  ERROR_STYLES,
  HINT_STYLES,
  INPUT_STYLES,
  LABEL_STYLES,
} from "./formStyles";

const SUBJECT_KINDS: { value: SubjectKind; label: string; hint: string }[] = [
  {
    value: "baseline",
    label: "Baseline",
    hint: "Reference is the baseline name, e.g. deterministic_rule.",
  },
  {
    value: "model_version",
    label: "Model version",
    hint: "Pick a registered model version to evaluate.",
  },
  {
    value: "reference",
    label: "Reference",
    hint: "Reference is an external reference id (URL, artifact URI, …).",
  },
];

/**
 * "Run evaluation" form on a benchmark (Phase 3).
 * Subject kind selector: baseline name | model version id | reference id.
 * On success shows a link to the new async run.
 */
export function RunEvaluationForm({
  benchmarkId,
  projectId,
  modelVersions,
}: {
  benchmarkId: string;
  projectId: string;
  modelVersions: { id: string; label: string }[];
}) {
  const router = useRouter();
  const [kind, setKind] = useState<SubjectKind>("baseline");
  const [baselineRef, setBaselineRef] = useState("");
  const [modelVersionId, setModelVersionId] = useState("");
  const [referenceRef, setReferenceRef] = useState("");
  const [name, setName] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState<EvaluationRun | null>(null);

  const ref =
    kind === "baseline"
      ? baselineRef.trim()
      : kind === "model_version"
        ? modelVersionId
        : referenceRef.trim();
  const canSubmit = !starting && ref !== "";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setStarting(true);
    setError(null);
    setStarted(null);
    try {
      const run = await startEvaluationRun(benchmarkId, {
        name: name.trim() === "" ? undefined : name.trim(),
        subject: { kind, ref: ref === "" ? null : ref },
      });
      setStarted(run);
      router.refresh();
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so the evaluation cannot be started."
          : err instanceof Error
            ? err.message
            : "Could not start the evaluation run.",
      );
    } finally {
      setStarting(false);
    }
  }

  const activeKind = SUBJECT_KINDS.find((k) => k.value === kind);

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-line bg-card p-5"
    >
      <h2 className="font-display text-base font-bold text-charcoal">
        Run evaluation
      </h2>
      <p className="mt-1 text-sm text-muted-ink">
        Evaluate a subject on this benchmark. Runs are async and cancellable.
      </p>

      {error && (
        <p role="alert" className={`${ERROR_STYLES} mt-4`}>
          {error}
        </p>
      )}
      {started && (
        <p
          role="status"
          className="mt-4 rounded-lg border border-line bg-platinum/40 px-3 py-2 text-sm text-charcoal"
        >
          Evaluation started —{" "}
          <Link
            href={`/projects/${projectId}/registry/benchmarks/${benchmarkId}/runs/${started.id}`}
            className="font-semibold underline decoration-charcoal underline-offset-4"
          >
            view run {started.name}
          </Link>
          .
        </p>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="eval-name" className={LABEL_STYLES}>
            Run name
          </label>
          <input
            id="eval-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="termination classifier v2"
            className={INPUT_STYLES}
          />
          <p className={HINT_STYLES}>
            Optional — defaults to a generated name.
          </p>
        </div>
        <fieldset>
          <legend className={LABEL_STYLES}>Subject kind</legend>
          <div className="flex overflow-hidden rounded-lg border border-line">
            {SUBJECT_KINDS.map((option) => {
              const active = kind === option.value;
              return (
                <label
                  key={option.value}
                  className={`flex-1 cursor-pointer transition-colors duration-200 ${
                    active
                      ? "bg-charcoal text-platinum"
                      : "bg-paper text-charcoal hover:bg-platinum"
                  }`}
                >
                  <input
                    type="radio"
                    name="subject-kind"
                    value={option.value}
                    checked={active}
                    onChange={() => setKind(option.value)}
                    className="peer sr-only"
                  />
                  <span className="flex min-h-[44px] items-center justify-center px-3 py-2 text-sm font-semibold peer-focus-visible:outline-3 peer-focus-visible:-outline-offset-3 peer-focus-visible:outline-platinum">
                    {option.label}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
      </div>

      <div className="mt-4">
        {kind === "baseline" && (
          <div>
            <label htmlFor="eval-baseline-ref" className={LABEL_STYLES}>
              Baseline name
            </label>
            <input
              id="eval-baseline-ref"
              type="text"
              required
              value={baselineRef}
              onChange={(e) => setBaselineRef(e.target.value)}
              placeholder="deterministic_rule"
              className={INPUT_STYLES}
            />
            <p className={HINT_STYLES}>{activeKind?.hint}</p>
          </div>
        )}
        {kind === "model_version" && (
          <div>
            <label htmlFor="eval-model-version" className={LABEL_STYLES}>
              Model version
            </label>
            <select
              id="eval-model-version"
              required
              value={modelVersionId}
              onChange={(e) => setModelVersionId(e.target.value)}
              className={INPUT_STYLES}
            >
              <option value="">Select a model version…</option>
              {modelVersions.map((mv) => (
                <option key={mv.id} value={mv.id}>
                  {mv.label}
                </option>
              ))}
            </select>
            <p className={HINT_STYLES}>{activeKind?.hint}</p>
          </div>
        )}
        {kind === "reference" && (
          <div>
            <label htmlFor="eval-reference-ref" className={LABEL_STYLES}>
              Reference id
            </label>
            <input
              id="eval-reference-ref"
              type="text"
              required
              value={referenceRef}
              onChange={(e) => setReferenceRef(e.target.value)}
              placeholder="artifacts://external/model-a"
              className={INPUT_STYLES}
            />
            <p className={HINT_STYLES}>{activeKind?.hint}</p>
          </div>
        )}
      </div>

      <div className="mt-4">
        <button type="submit" disabled={!canSubmit} className={BUTTON_PRIMARY}>
          {starting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Play className="h-4 w-4" aria-hidden="true" />
          )}
          {starting ? "Starting…" : "Start evaluation"}
        </button>
      </div>
    </form>
  );
}
