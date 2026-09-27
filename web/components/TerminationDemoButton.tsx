"use client";

import { FlaskConical, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { isApiOfflineError, runTerminationDemo } from "../lib/api";

/**
 * "Try the termination demo" button. POSTs the demo endpoint, which seeds
 * the §7 termination fixture (spec + dataset + version) and runs the
 * baseline evaluation, then redirects to the created spec.
 */
export function TerminationDemoButton({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle() {
    setPending(true);
    setError(null);
    try {
      const result = await runTerminationDemo(projectId);
      router.push(`/projects/${projectId}/specs/${result.spec.id}`);
    } catch (err) {
      if (isApiOfflineError(err)) {
        setError(
          "The API is offline, so the demo cannot run. Start the backend at http://localhost:8000 and try again.",
        );
      } else {
        setError(
          err instanceof Error ? err.message : "The demo failed to run.",
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        disabled={pending}
        onClick={handle}
        className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <FlaskConical className="h-4 w-4" aria-hidden="true" />
        )}
        {pending ? "Running demo…" : "Try the termination demo"}
      </button>
      <p className="mt-2 max-w-md text-xs leading-5 text-muted-ink">
        Seeds the sample “Search termination intelligence” spec, dataset, and
        baseline evaluation so you can explore the fabrication flow end to end.
      </p>
      {error && (
        <p
          role="alert"
          className="mt-3 max-w-md rounded-lg bg-[#DC2626]/10 px-3.5 py-2.5 text-sm font-medium text-[#8f1d1d]"
        >
          {error}
        </p>
      )}
    </div>
  );
}
