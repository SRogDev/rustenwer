"use client";

import { useState } from "react";
import type { InferenceResponse } from "../../shared/types";
import { inferDeployment } from "../lib/api";
import { INPUT_STYLES, LABEL_STYLES } from "./formStyles";

/**
 * Test console for a deployment: type JSON inputs, run inference,
 * see the machine-readable output. Client component.
 */
export function InferConsole({
  deploymentId,
  inputSchema,
}: {
  deploymentId: string;
  inputSchema: Record<string, unknown> | null;
}) {
  const [inputsText, setInputsText] = useState("{}");
  const [response, setResponse] = useState<InferenceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(inputsText) as Record<string, unknown>;
    } catch {
      setError("Inputs must be valid JSON.");
      return;
    }
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const result = await inferDeployment(deploymentId, parsed);
      setResponse(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Inference request failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      {inputSchema && Object.keys(inputSchema).length > 0 && (
        <details className="mb-4 rounded-lg border border-line bg-paper p-3">
          <summary className="cursor-pointer text-sm font-semibold text-charcoal">
            Expected input schema
          </summary>
          <pre className="mt-2 overflow-x-auto font-mono text-xs text-muted-ink">
            {JSON.stringify(inputSchema, null, 2)}
          </pre>
        </details>
      )}
      <label className={LABEL_STYLES}>
        Inputs (JSON)
        <textarea
          className={`${INPUT_STYLES} min-h-28 font-mono text-[13px]`}
          value={inputsText}
          onChange={(e) => setInputsText(e.target.value)}
          spellCheck={false}
          aria-label="Inference inputs as JSON"
        />
      </label>
      <button
        type="button"
        onClick={run}
        disabled={loading}
        className="mt-3 inline-flex min-h-[44px] items-center rounded-lg bg-charcoal px-4 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Running…" : "Run inference"}
      </button>
      <div className="mt-4" aria-live="polite">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {response && (
          <div className="space-y-3">
            <div>
              <h4 className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                Output
              </h4>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-platinum/40 px-4 py-3 font-mono text-[13px] text-charcoal">
                {JSON.stringify(response.output, null, 2)}
              </pre>
            </div>
            <p className="font-mono text-xs text-muted-ink">
              primitive: {response.primitive} · provider: {response.provider} ·{" "}
              {response.latency_ms.toFixed(1)} ms
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
