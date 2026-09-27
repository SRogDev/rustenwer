"use client";

import { useState } from "react";
import type { ModelVersion } from "../../shared/types";
import { INPUT_STYLES, LABEL_STYLES } from "./formStyles";

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Lineage fields compared between two versions. */
const DIFF_FIELDS: {
  key:
    | "dataset_version_id"
    | "training_strategy"
    | "code_version"
    | "template_version"
    | "seed"
    | "base_model"
    | "training_run_id"
    | "architecture"
    | "size_bytes"
    | "metrics"
    | "artifact_uri";
  label: string;
}[] = [
  { key: "dataset_version_id", label: "Dataset version" },
  { key: "training_strategy", label: "Training strategy" },
  { key: "code_version", label: "Code version" },
  { key: "template_version", label: "Template version" },
  { key: "seed", label: "Seed" },
  { key: "base_model", label: "Base model" },
  { key: "training_run_id", label: "Training run" },
  { key: "architecture", label: "Architecture" },
  { key: "size_bytes", label: "Size (bytes)" },
  { key: "metrics", label: "Metrics" },
  { key: "artifact_uri", label: "Artifact URI" },
];

interface FieldDiff {
  field: string;
  from: string;
  to: string;
}

/**
 * "What changed between versions" diff explorer (Phase 3 registry).
 * Picks any two versions and lists the lineage fields that differ.
 * Computed client-side from the immutable version records, so it also
 * works offline.
 */
export function ModelVersionDiff({ versions }: { versions: ModelVersion[] }) {
  const sorted = [...versions].sort((a, b) => a.version - b.version);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const [fromId, setFromId] = useState<string>(first?.id ?? "");
  const [toId, setToId] = useState<string>(last?.id ?? "");

  const from = sorted.find((v) => v.id === fromId) ?? first;
  const to = sorted.find((v) => v.id === toId) ?? last;

  const diffs: FieldDiff[] =
    from && to && from.id !== to.id
      ? DIFF_FIELDS.flatMap(({ key, label }) => {
          const a = stringify(from[key]);
          const b = stringify(to[key]);
          return a === b ? [] : [{ field: label, from: a, to: b }];
        })
      : [];

  if (sorted.length < 2) {
    return (
      <p className="text-sm text-muted-ink">
        Only one version is registered — nothing to compare yet.
      </p>
    );
  }

  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="diff-from" className={LABEL_STYLES}>
            From version
          </label>
          <select
            id="diff-from"
            value={from?.id ?? ""}
            onChange={(e) => setFromId(e.target.value)}
            className={INPUT_STYLES}
          >
            {sorted.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.version}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="diff-to" className={LABEL_STYLES}>
            To version
          </label>
          <select
            id="diff-to"
            value={to?.id ?? ""}
            onChange={(e) => setToId(e.target.value)}
            className={INPUT_STYLES}
          >
            {sorted.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.version}
              </option>
            ))}
          </select>
        </div>
      </div>

      {from && to && from.id === to.id ? (
        <p className="mt-4 text-sm text-muted-ink">
          Pick two different versions to see what changed.
        </p>
      ) : diffs.length === 0 ? (
        <p className="mt-4 text-sm text-muted-ink">
          No lineage differences between v{from?.version} and v{to?.version} —
          the change is metadata-only.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead>
              <tr className="border-b border-line bg-platinum/40">
                <th
                  scope="col"
                  className="px-4 py-3 text-xs font-semibold tracking-wide text-muted-ink uppercase"
                >
                  Field
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-xs font-semibold tracking-wide text-muted-ink uppercase"
                >
                  v{from?.version}
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-xs font-semibold tracking-wide text-muted-ink uppercase"
                >
                  v{to?.version}
                </th>
              </tr>
            </thead>
            <tbody>
              {diffs.map((diff) => (
                <tr
                  key={diff.field}
                  className="border-b border-line align-top last:border-0"
                >
                  <th
                    scope="row"
                    className="px-4 py-3 text-xs font-semibold text-muted-ink"
                  >
                    {diff.field}
                  </th>
                  <td className="max-w-xs px-4 py-3 font-mono text-[13px] break-words text-ink">
                    {diff.from}
                  </td>
                  <td className="max-w-xs px-4 py-3 font-mono text-[13px] break-words font-semibold text-charcoal">
                    {diff.to}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
