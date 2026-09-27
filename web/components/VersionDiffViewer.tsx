"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  IntelligenceVersion,
  IntelligenceVersionDiff,
} from "../../shared/types";
import { getIntelligenceVersionDiff } from "../lib/api";
import { INPUT_STYLES, LABEL_STYLES } from "./formStyles";

function SectionTitle({ children }: { children: string }) {
  return (
    <h4 className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
      {children}
    </h4>
  );
}

function ComponentList({ items }: { items: Record<string, unknown>[] }) {
  if (items.length === 0)
    return <p className="text-sm text-muted-ink">None.</p>;
  return (
    <ul className="mt-2 space-y-1.5">
      {items.map((item, index) => {
        const record = item as Record<string, unknown>;
        const label =
          typeof record.label === "string" && record.label
            ? record.label
            : String(record.kind ?? `component ${index}`);
        return (
          <li
            key={`${label}-${String(record.kind ?? "component")}`}
            className="rounded-lg bg-platinum/40 px-3 py-2 font-mono text-[13px] text-charcoal"
          >
            {label}
            <span className="ml-2 text-muted-ink">
              ({String(record.kind ?? "?")})
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Client-side diff viewer: pick two versions, fetch the structural diff,
 * render architecture-kind changes plus added/removed/modified components.
 */
export function VersionDiffViewer({
  intelligenceId,
  versions,
}: {
  intelligenceId: string;
  versions: IntelligenceVersion[];
}) {
  const sorted = [...versions].sort((a, b) => a.version - b.version);
  const newest = sorted[sorted.length - 1];
  const previous = sorted[sorted.length - 2];
  // Default comparison: the two newest versions.
  const [fromVersion, setFromVersion] = useState<number | null>(
    previous?.version ?? null,
  );
  const [toVersion, setToVersion] = useState<number | null>(
    newest?.version ?? null,
  );
  const [diff, setDiff] = useState<IntelligenceVersionDiff | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (fromVersion === null || toVersion === null) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getIntelligenceVersionDiff(
        intelligenceId,
        fromVersion,
        toVersion,
      );
      setDiff(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load diff.");
      setDiff(null);
    } finally {
      setLoading(false);
    }
  }, [intelligenceId, fromVersion, toVersion]);

  useEffect(() => {
    void load();
  }, [load]);

  if (sorted.length < 2) {
    return (
      <p className="text-sm text-muted-ink">
        Publish a second version to compare architectures.
      </p>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <label className={LABEL_STYLES}>
          From
          <select
            className={INPUT_STYLES}
            value={fromVersion ?? ""}
            onChange={(e) => setFromVersion(Number(e.target.value))}
            aria-label="Compare from version"
          >
            {sorted.map((v) => (
              <option key={v.id} value={v.version}>
                v{v.version}
              </option>
            ))}
          </select>
        </label>
        <label className={LABEL_STYLES}>
          To
          <select
            className={INPUT_STYLES}
            value={toVersion ?? ""}
            onChange={(e) => setToVersion(Number(e.target.value))}
            aria-label="Compare to version"
          >
            {sorted.map((v) => (
              <option key={v.id} value={v.version}>
                v{v.version}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4" aria-live="polite">
        {loading && <p className="text-sm text-muted-ink">Loading diff…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {diff && !loading && (
          <div className="space-y-4">
            {diff.architecture_kind_changed && (
              <div>
                <SectionTitle>Architecture kind changed</SectionTitle>
                <p className="mt-2 text-sm text-charcoal">
                  The two versions use different architecture kinds.
                </p>
              </div>
            )}
            <div>
              <SectionTitle>Added components</SectionTitle>
              <ComponentList items={diff.components_added} />
            </div>
            <div>
              <SectionTitle>Removed components</SectionTitle>
              <ComponentList items={diff.components_removed} />
            </div>
            <div>
              <SectionTitle>Modified components</SectionTitle>
              {diff.components_modified.length === 0 ? (
                <p className="text-sm text-muted-ink">None.</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {diff.components_modified.map((item) => {
                    const record = item as Record<string, unknown>;
                    const changed = Array.isArray(record.changed_config_keys)
                      ? (record.changed_config_keys as string[])
                      : [];
                    return (
                      <li
                        key={String(record.label ?? record.kind ?? "component")}
                        className="rounded-lg border border-line bg-paper p-3"
                      >
                        <p className="font-mono text-[13px] font-semibold text-charcoal">
                          {String(record.label ?? record.kind ?? "?")}
                        </p>
                        {changed.length > 0 && (
                          <p className="mt-1 font-mono text-xs text-muted-ink">
                            config changed: {changed.join(", ")}
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            {diff.notes.length > 0 && (
              <div>
                <SectionTitle>Notes</SectionTitle>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-ink">
                  {diff.notes.map((note) => (
                    <li key={note.slice(0, 48)}>{note}</li>
                  ))}
                </ul>
              </div>
            )}
            {!diff.architecture_kind_changed &&
              !diff.schema_changed &&
              diff.components_added.length === 0 &&
              diff.components_removed.length === 0 &&
              diff.components_modified.length === 0 && (
                <p className="text-sm text-muted-ink">
                  No structural changes between these versions.
                </p>
              )}
          </div>
        )}
      </div>
    </div>
  );
}
