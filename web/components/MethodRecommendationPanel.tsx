"use client";

import { Ban, CheckCircle2, Loader2, Wand2 } from "lucide-react";
import { useState } from "react";
import type {
  DiagnosisResult,
  Evaluation,
  IntelligenceSpec,
  MethodRank,
  MethodVeto,
} from "../../shared/types";
import { getSpec, isApiOfflineError, MOCK_SPECS } from "../lib/api";
import {
  baselineReportFromEvaluation,
  isMethodsApiOfflineError,
  type MethodRecommendation,
  MOCK_METHOD_RECOMMENDATION,
  recommendMethods,
} from "../lib/methods";

function RankedMethod({ rank, index }: { rank: MethodRank; index: number }) {
  return (
    <li className="rounded-xl border border-line bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-charcoal font-display text-sm font-bold text-platinum"
            aria-hidden="true"
          >
            {index + 1}
          </span>
          <div>
            <h4 className="font-display text-base font-bold text-charcoal">
              <span className="font-mono">{rank.slug}</span>
              <span className="ml-2 font-mono text-xs font-semibold text-muted-ink">
                v{rank.version}
              </span>
            </h4>
            <p className="mt-0.5 text-xs font-semibold text-muted-ink">
              score {rank.score.toFixed(2)}
            </p>
          </div>
        </div>
        <CheckCircle2
          className="h-5 w-5 shrink-0 text-charcoal"
          aria-hidden="true"
        />
      </div>
      <p className="mt-3 text-xs font-semibold tracking-wide text-muted-ink uppercase">
        Use {rank.slug} because…
      </p>
      <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-6 text-charcoal">
        {rank.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </li>
  );
}

function VetoedMethod({ veto }: { veto: MethodVeto }) {
  return (
    <li className="rounded-xl border-2 border-charcoal bg-platinum p-5">
      <div className="flex items-start gap-3">
        <Ban
          className="mt-0.5 h-5 w-5 shrink-0 text-[#8f1d1d]"
          aria-hidden="true"
        />
        <div>
          <h4 className="font-display text-base font-bold text-charcoal">
            <span className="font-mono">{veto.slug}</span>
            <span className="ml-2 font-mono text-xs font-semibold text-muted-ink">
              v{veto.version}
            </span>
          </h4>
          <p className="mt-1.5 text-sm leading-6 text-charcoal">
            <span className="font-semibold">
              Ruled out {veto.slug} because…{" "}
            </span>
            {veto.reason}
          </p>
        </div>
      </div>
    </li>
  );
}

/**
 * "Method recommendation" section for the spec detail page (Phase 5 plan §8).
 * Calls POST /api/v1/methods/recommend for the current spec and renders the
 * ranked methods with reasons plus the vetoed list with reasons — the
 * negative-search seed for Phase 7.
 */
export function MethodRecommendationPanel({
  specId,
  diagnosis,
  evaluations,
}: {
  specId: string;
  diagnosis: DiagnosisResult | null;
  evaluations: Evaluation[];
}) {
  const [recommendation, setRecommendation] =
    useState<MethodRecommendation | null>(null);
  const [mock, setMock] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [allowGeneric, setAllowGeneric] = useState(false);

  async function handleRecommend() {
    setBusy(true);
    setError(null);
    try {
      // When the API is offline we fall back to the mock spec + the mock
      // recommendation (the Phase 5 seeding contract rendered locally) and
      // label both as mock — the same honest pattern Phase 0 established.
      let spec: IntelligenceSpec;
      try {
        spec = await getSpec(specId);
      } catch (err) {
        if (!isApiOfflineError(err)) throw err;
        spec =
          MOCK_SPECS.find((s) => s.id === specId) ??
          (MOCK_SPECS[0] as IntelligenceSpec);
      }
      let recommendationResult: MethodRecommendation;
      let servedMock = false;
      try {
        // Newest completed evaluation first — the baseline bar (Rule 9).
        const latestWithResults = evaluations.find((e) => e.results);
        recommendationResult = await recommendMethods({
          spec,
          diagnosis,
          baseline_report: baselineReportFromEvaluation(
            specId,
            latestWithResults,
          ),
          allow_generic: allowGeneric,
        });
      } catch (err) {
        if (!isMethodsApiOfflineError(err)) throw err;
        recommendationResult = MOCK_METHOD_RECOMMENDATION;
        servedMock = true;
      }
      setRecommendation(recommendationResult);
      setMock(servedMock);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Recommendation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-line bg-card p-5 sm:p-6">
      <h3 className="flex items-center gap-2 font-display text-lg font-bold text-charcoal">
        <Wand2 className="h-5 w-5" aria-hidden="true" />
        Method recommendation
      </h3>
      <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-ink">
        The registry-driven recommendation engine (plan §3) ranks compatible
        training methods for this spec — and records explicit vetoes with
        reasons, the negative-search seed for Phase 7.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={handleRecommend}
          className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Wand2 className="h-4 w-4" aria-hidden="true" />
          )}
          {busy
            ? "Recommending…"
            : recommendation
              ? "Re-run recommendation"
              : "Recommend methods"}
        </button>
        <label
          htmlFor="allow-generic"
          className="flex min-h-[44px] cursor-pointer items-center gap-2 text-sm font-medium text-charcoal"
        >
          <input
            id="allow-generic"
            type="checkbox"
            checked={allowGeneric}
            onChange={(e) => setAllowGeneric(e.target.checked)}
            className="h-4 w-4 accent-[#16161A]"
          />
          Consider generic methods
          <span className="text-xs font-normal text-muted-ink">
            (e.g. contrastive for non-retrieval primitives)
          </span>
        </label>
      </div>

      {!diagnosis && !recommendation && (
        <p className="mt-3 text-sm text-muted-ink">
          Tip: diagnose the spec first — the recommendation is sharper with a
          diagnosis and a baseline evaluation in place.
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-lg bg-[#DC2626]/10 px-3.5 py-2.5 text-sm font-medium text-[#8f1d1d]"
        >
          {error}
        </p>
      )}

      {recommendation && (
        <div className="mt-6 space-y-8">
          {mock && (
            <p
              role="status"
              className="rounded-lg bg-platinum px-3.5 py-2.5 text-sm font-medium text-charcoal"
            >
              Mock recommendation — the API is offline, so this is the Phase 5
              seeding contract rendered locally. Start the backend for the live
              recommendation engine.
            </p>
          )}

          {recommendation.note && (
            <p
              role="status"
              className="rounded-xl border-2 border-charcoal bg-platinum p-5 text-sm leading-6 text-charcoal"
            >
              {recommendation.note}
            </p>
          )}

          {recommendation.recommended.length > 0 && (
            <div>
              <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                Recommended — ranked by spec fit
              </p>
              <ul className="mt-3 space-y-3">
                {recommendation.recommended.map((rank, index) => (
                  <RankedMethod key={rank.slug} rank={rank} index={index} />
                ))}
              </ul>
            </div>
          )}

          {recommendation.vetoed.length > 0 && (
            <div>
              <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                Ruled out — negative-search seeds for Phase 7
              </p>
              <ul className="mt-3 space-y-3">
                {recommendation.vetoed.map((veto) => (
                  <VetoedMethod key={veto.slug} veto={veto} />
                ))}
              </ul>
            </div>
          )}

          {recommendation.citations.length > 0 && (
            <div className="border-t border-line pt-4">
              <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                Method citations
              </p>
              <p className="mt-1.5 font-mono text-sm text-charcoal">
                {recommendation.citations.join(" · ")}
              </p>
              <p className="mt-1 text-xs text-muted-ink">
                The Strategy Agent pins these citations into the training
                strategy (plan §5).
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
