"use client";

import { Info, Loader2, Lock } from "lucide-react";
import { useState } from "react";
import { ApiError, isApiOfflineError, promoteIntelligence } from "../lib/api";
import { BUTTON_SECONDARY, ERROR_STYLES } from "./formStyles";

/**
 * Promote button for an intelligence (Phase 3 registry).
 * Promotion logic lands in Phase 6: the button calls the endpoint anyway
 * and surfaces the backend's 501 response honestly instead of hiding it.
 */
export function PromoteIntelligenceButton({
  intelligenceId,
}: {
  intelligenceId: string;
}) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [is501, setIs501] = useState(false);

  async function handlePromote() {
    setPending(true);
    setMessage(null);
    setIs501(false);
    try {
      await promoteIntelligence(intelligenceId);
      setMessage(
        "Promotion succeeded (unexpected — promotion lands in Phase 6).",
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) {
        setIs501(true);
        setMessage(`501 Not Implemented — ${err.message}`);
      } else {
        setMessage(
          isApiOfflineError(err)
            ? "The API is offline, so the promote call cannot be made."
            : err instanceof Error
              ? err.message
              : "Promote failed.",
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="rounded-xl border border-line bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-bold text-charcoal">
            Promote intelligence
          </h2>
          <p className="mt-1 text-sm text-muted-ink">
            Promotion logic lands in Phase 6. The button calls the endpoint
            anyway so you can see the honest backend response.
          </p>
        </div>
        <button
          type="button"
          onClick={handlePromote}
          disabled={pending}
          className={BUTTON_SECONDARY}
          title="Promotion is not implemented yet (Phase 6)"
        >
          {pending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Lock className="h-4 w-4" aria-hidden="true" />
          )}
          {pending ? "Promoting…" : "Promote — Phase 6"}
        </button>
      </div>
      {message && (
        <p
          role="alert"
          className={`mt-4 flex items-start gap-2 rounded-lg px-3 py-2 text-sm ${
            is501
              ? "border border-line bg-platinum/40 text-charcoal"
              : ERROR_STYLES
          }`}
        >
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {message}
        </p>
      )}
    </div>
  );
}
