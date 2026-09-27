"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { DeploymentStatus } from "../../shared/types";
import { isApiOfflineError, patchDeployment } from "../lib/api";

/** Deployment lifecycle: DRAFT -> ACTIVE <-> PAUSED, * -> ARCHIVED. */
const ACTIONS: {
  label: string;
  to: DeploymentStatus;
  from: DeploymentStatus[];
}[] = [
  { label: "Activate", to: "ACTIVE", from: ["DRAFT", "PAUSED"] },
  { label: "Pause", to: "PAUSED", from: ["ACTIVE"] },
  { label: "Archive", to: "ARCHIVED", from: ["DRAFT", "ACTIVE", "PAUSED"] },
];

export function DeploymentStatusButtons({
  deploymentId,
  status,
}: {
  deploymentId: string;
  status: DeploymentStatus;
}) {
  const router = useRouter();
  const [pending, setPending] = useState<DeploymentStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const available = ACTIONS.filter((a) =>
    (a.from as string[]).includes(status as string),
  );
  if (available.length === 0) return null;

  async function handle(to: DeploymentStatus) {
    setPending(to);
    setError(null);
    try {
      await patchDeployment(deploymentId, { status: to });
      router.refresh();
    } catch (err) {
      if (isApiOfflineError(err)) {
        setError("The API is offline, so the deployment cannot be updated.");
      } else {
        setError(err instanceof Error ? err.message : "Transition failed.");
      }
    } finally {
      setPending(null);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {available.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => void handle(action.to)}
            disabled={pending !== null}
            className="inline-flex min-h-[44px] items-center rounded-lg border border-line bg-card px-4 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pending === action.to ? "Working…" : action.label}
          </button>
        ))}
      </div>
      {error && (
        <p className="mt-2 text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
