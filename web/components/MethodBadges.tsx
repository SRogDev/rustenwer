import { Cpu } from "lucide-react";
import type { MethodValidationStatus } from "../../shared/types";

/**
 * Phase 5 badges: VALIDATED (a real local/GPU run exists) vs KNOWN
 * (taxonomy entry, not yet validated on our stack), plus the locally-runnable
 * indicator. Platinum theme only.
 */
export function MethodBadges({
  status,
  locallyRunnable,
}: {
  status: MethodValidationStatus;
  locallyRunnable: boolean;
}) {
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span
        className={`inline-flex min-h-[28px] items-center rounded-full px-3 py-1 text-xs font-semibold tracking-wide uppercase ${
          status === "VALIDATED"
            ? "bg-charcoal text-platinum"
            : "bg-platinum text-muted-ink"
        }`}
      >
        {status}
      </span>
      {locallyRunnable && (
        <span className="inline-flex min-h-[28px] items-center gap-1.5 rounded-full border border-charcoal bg-paper px-3 py-1 text-xs font-semibold tracking-wide text-charcoal uppercase">
          <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
          Runs locally
        </span>
      )}
    </span>
  );
}
