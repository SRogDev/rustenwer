"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type {
  Intelligence,
  IntelligenceSpec,
  IntelligenceVersion,
} from "../../shared/types";
import { createDeployment } from "../lib/api";
import { INPUT_STYLES, LABEL_STYLES } from "./formStyles";

/**
 * Deploy flow: pick an immutable intelligence version, a spec, a name —
 * the deployment pins that exact version snapshot forever.
 */
export function DeployIntelligenceForm({
  projectId,
  intelligences,
  versionsByIntelligence,
  specs,
  preselectedVersionId,
}: {
  projectId: string;
  intelligences: Intelligence[];
  versionsByIntelligence: Record<string, IntelligenceVersion[]>;
  specs: IntelligenceSpec[];
  preselectedVersionId?: string;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [specId, setSpecId] = useState(specs[0]?.id ?? "");
  const [versionId, setVersionId] = useState(preselectedVersionId ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const versionOptions = useMemo(
    () =>
      intelligences.flatMap((intel) =>
        (versionsByIntelligence[intel.id] ?? []).map((v) => ({
          id: v.id,
          label: `${intel.name} v${v.version}`,
        })),
      ),
    [intelligences, versionsByIntelligence],
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !specId || !versionId) {
      setError("Name, spec, and intelligence version are all required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const deployment = await createDeployment(projectId, {
        name: name.trim(),
        spec_id: specId,
        intelligence_version_id: versionId,
      });
      router.push(`/projects/${projectId}/deployments/${deployment.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deploy failed.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <label className={LABEL_STYLES}>
        Deployment name
        <input
          className={INPUT_STYLES}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="prod termination gate"
          aria-label="Deployment name"
        />
      </label>
      <label className={LABEL_STYLES}>
        Intelligence version (immutable snapshot)
        <select
          className={INPUT_STYLES}
          value={versionId}
          onChange={(e) => setVersionId(e.target.value)}
          aria-label="Intelligence version"
        >
          <option value="">Select a version…</option>
          {versionOptions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className={LABEL_STYLES}>
        Spec
        <select
          className={INPUT_STYLES}
          value={specId}
          onChange={(e) => setSpecId(e.target.value)}
          aria-label="Spec"
        >
          {specs.map((spec) => (
            <option key={spec.id} value={spec.id}>
              {spec.name}
            </option>
          ))}
        </select>
      </label>
      <p className="text-sm leading-6 text-muted-ink">
        The deployment serves the exact immutable snapshot of the selected
        version — architecture, pinned model refs, input/output schemas —
        through the hosted provider. New versions never change a live
        deployment.
      </p>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={submitting}
        className="inline-flex min-h-[44px] items-center rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? "Deploying…" : "Deploy"}
      </button>
    </form>
  );
}
