import { WifiOff } from "lucide-react";

/**
 * Visible banner shown whenever the UI is serving mock data because the
 * Rustenwer API is unreachable. Honest labeling is a Phase 0 requirement.
 */
export function OfflineBanner() {
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-xl bg-charcoal px-4 py-3 text-platinum sm:items-center"
    >
      <WifiOff className="mt-0.5 h-5 w-5 shrink-0 sm:mt-0" aria-hidden="true" />
      <p className="text-sm font-medium">
        API offline — showing mock data (Phase 0). Start the backend at{" "}
        <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[13px]">
          http://localhost:8000
        </code>{" "}
        to see live projects.
      </p>
    </div>
  );
}
