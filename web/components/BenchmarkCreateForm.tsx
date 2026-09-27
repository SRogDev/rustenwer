"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createBenchmark, isApiOfflineError } from "../lib/api";
import {
  BUTTON_PRIMARY,
  ERROR_STYLES,
  HINT_STYLES,
  INPUT_STYLES,
  LABEL_STYLES,
} from "./formStyles";

/**
 * Create-benchmark form (Phase 3 registry).
 * Fields: name, description, evaluation function, metrics (comma-separated).
 */
export function BenchmarkCreateForm({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [evaluationFunction, setEvaluationFunction] = useState("");
  const [metrics, setMetrics] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim().length > 0 && !saving;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      await createBenchmark(projectId, {
        name: name.trim(),
        description: description.trim() === "" ? undefined : description.trim(),
        evaluation_function:
          evaluationFunction.trim() === ""
            ? undefined
            : evaluationFunction.trim(),
        metrics:
          metrics.trim() === ""
            ? undefined
            : metrics
                .split(",")
                .map((m) => m.trim())
                .filter((m) => m !== ""),
      });
      setName("");
      setDescription("");
      setEvaluationFunction("");
      setMetrics("");
      router.refresh();
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so the benchmark cannot be created."
          : err instanceof Error
            ? err.message
            : "Could not create the benchmark.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-line bg-card p-5"
    >
      <h3 className="font-display text-base font-bold text-charcoal">
        New benchmark
      </h3>
      <p className="mt-1 text-sm text-muted-ink">
        Benchmarks are reusable across candidate architectures.
      </p>

      {error && (
        <p role="alert" className={`${ERROR_STYLES} mt-4`}>
          {error}
        </p>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="benchmark-name" className={LABEL_STYLES}>
            Name
          </label>
          <input
            id="benchmark-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="invoice-anomaly"
            className={INPUT_STYLES}
          />
        </div>
        <div>
          <label htmlFor="benchmark-eval-fn" className={LABEL_STYLES}>
            Evaluation function
          </label>
          <input
            id="benchmark-eval-fn"
            type="text"
            value={evaluationFunction}
            onChange={(e) => setEvaluationFunction(e.target.value)}
            placeholder="accuracy_on_labeled_steps"
            className={INPUT_STYLES}
          />
        </div>
      </div>

      <div className="mt-4">
        <label htmlFor="benchmark-description" className={LABEL_STYLES}>
          Description
        </label>
        <textarea
          id="benchmark-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="What does this benchmark measure?"
          className={INPUT_STYLES}
        />
      </div>

      <div className="mt-4">
        <label htmlFor="benchmark-metrics" className={LABEL_STYLES}>
          Metrics
        </label>
        <input
          id="benchmark-metrics"
          type="text"
          value={metrics}
          onChange={(e) => setMetrics(e.target.value)}
          placeholder="accuracy, latency_ms_p50, cost_usd_per_1k"
          className={INPUT_STYLES}
        />
        <p className={HINT_STYLES}>Comma-separated metric names.</p>
      </div>

      <div className="mt-4">
        <button type="submit" disabled={!canSubmit} className={BUTTON_PRIMARY}>
          {saving && (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          {saving ? "Creating…" : "Create benchmark"}
        </button>
      </div>
    </form>
  );
}
