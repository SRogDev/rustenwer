"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Upload,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import type {
  Dataset,
  DatasetReport,
  DatasetVersion,
} from "../../shared/types";
import {
  createDatasetVersion,
  isApiOfflineError,
  listDatasetVersions,
  MOCK_DATASET_VERSIONS,
  validateDatasetVersion,
} from "../lib/api";

/** Validation report panel: schema, class balance, leakage, split, readiness. */
function ValidationReport({ report }: { report: DatasetReport }) {
  const total = report.row_count;
  const balance = report.class_balance;
  return (
    <div className="mt-3 rounded-lg border border-line bg-paper p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-display text-sm font-bold text-charcoal">
          Validation report — v{report.version}
        </h4>
        {report.ready_for_training ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-charcoal px-3 py-1 text-xs font-semibold text-platinum">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
            Ready for training
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#DC2626]/10 px-3 py-1 text-xs font-semibold text-[#8f1d1d]">
            <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
            Not ready
          </span>
        )}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Column schema ({total} rows)
          </p>
          <dl className="mt-1.5 space-y-1 text-sm">
            {Object.entries(report.column_schema).map(([column, type]) => (
              <div key={column} className="flex justify-between gap-2">
                <dt className="font-mono text-[13px] text-charcoal">
                  {column}
                </dt>
                <dd className="text-muted-ink">{type}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Class balance
          </p>
          {balance ? (
            <ul className="mt-1.5 space-y-1.5 text-sm">
              {Object.entries(balance).map(([label, count]) => {
                const pct = total > 0 ? (count / total) * 100 : 0;
                return (
                  <li key={label}>
                    <div className="flex justify-between gap-2 text-charcoal">
                      <span className="font-medium">{label}</span>
                      <span className="text-muted-ink">
                        {count} ({pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div
                      className="mt-1 h-1.5 overflow-hidden rounded-full bg-platinum"
                      role="img"
                      aria-label={`${label}: ${count} of ${total}`}
                    >
                      <div
                        className="h-full rounded-full bg-charcoal transition-[width] duration-300"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-1.5 text-sm text-muted-ink">
              No label column declared.
            </p>
          )}
          {report.imbalance_detected && (
            <p className="mt-2 flex items-start gap-1.5 text-xs font-medium text-[#8f1d1d]">
              <AlertTriangle
                className="mt-0.5 h-3.5 w-3.5 shrink-0"
                aria-hidden="true"
              />
              Imbalance detected: minority class is under 20% of the majority.
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Leakage flags
          </p>
          {report.leakage_flags.length === 0 ? (
            <p className="mt-1.5 text-sm text-charcoal">None — clean.</p>
          ) : (
            <ul className="mt-1.5 space-y-1 text-sm">
              {report.leakage_flags.map((flag) => (
                <li
                  key={flag}
                  className="flex items-start gap-1.5 font-medium text-[#8f1d1d]"
                >
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0"
                    aria-hidden="true"
                  />
                  {flag}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Recommended split
          </p>
          <p className="mt-1.5 font-mono text-sm text-charcoal">
            train {report.recommended_split.train} · validation{" "}
            {report.recommended_split.validation} · test{" "}
            {report.recommended_split.test}
          </p>
          {Object.keys(report.missing_values).length > 0 && (
            <p className="mt-2 text-xs text-muted-ink">
              Missing values:{" "}
              {Object.entries(report.missing_values)
                .map(([col, n]) => `${col} (${n})`)
                .join(", ")}
            </p>
          )}
        </div>
      </div>

      {report.notes.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-line pt-3 text-xs leading-5 text-muted-ink">
          {report.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * One dataset card: version list, version upload (JSON array rows + label
 * column), and per-version validation report view.
 */
export function DatasetCard({ dataset }: { dataset: Dataset }) {
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [rowsText, setRowsText] = useState("");
  const [labelColumn, setLabelColumn] = useState("");
  const [uploading, setUploading] = useState(false);
  const [validating, setValidating] = useState<number | null>(null);
  const [openReport, setOpenReport] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDatasetVersions(dataset.id)
      .then((list) => {
        if (!cancelled) setVersions(list);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (isApiOfflineError(err)) {
          setOffline(true);
          setVersions(
            MOCK_DATASET_VERSIONS.filter((v) => v.dataset_id === dataset.id),
          );
        } else {
          setError(
            err instanceof Error ? err.message : "Failed to load versions.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dataset.id]);

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    let rows: unknown;
    try {
      rows = JSON.parse(rowsText) as unknown;
    } catch (err) {
      setError(
        `Rows are not valid JSON: ${err instanceof Error ? err.message : "parse error"}.`,
      );
      return;
    }
    if (!Array.isArray(rows) || rows.length === 0) {
      setError("Rows must be a non-empty JSON array of objects.");
      return;
    }
    if (rows.some((r) => typeof r !== "object" || r === null)) {
      setError("Every row must be a JSON object.");
      return;
    }
    setUploading(true);
    try {
      const version = await createDatasetVersion(dataset.id, {
        rows: rows as Record<string, unknown>[],
        ...(labelColumn.trim() ? { label_column: labelColumn.trim() } : {}),
      });
      setVersions((prev) => [...prev, version]);
      setRowsText("");
      setOpenReport(version.version);
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so the version could not be uploaded."
          : err instanceof Error
            ? err.message
            : "Version upload failed.",
      );
    } finally {
      setUploading(false);
    }
  }

  async function handleValidate(version: DatasetVersion) {
    setValidating(version.version);
    setError(null);
    try {
      const report = await validateDatasetVersion(dataset.id, version.version);
      setVersions((prev) =>
        prev.map((v) => (v.id === version.id ? { ...v, stats: report } : v)),
      );
      setOpenReport(version.version);
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so the version could not be revalidated."
          : err instanceof Error
            ? err.message
            : "Validation failed.",
      );
    } finally {
      setValidating(null);
    }
  }

  return (
    <article className="rounded-xl border border-line bg-card p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-bold text-charcoal">
            {dataset.name}
          </h3>
          {dataset.description && (
            <p className="mt-1 text-sm leading-6 text-muted-ink">
              {dataset.description}
            </p>
          )}
        </div>
        <span className="rounded-full bg-platinum px-3 py-1 text-xs font-semibold text-charcoal">
          {dataset.row_count} rows · {versions.length} version
          {versions.length === 1 ? "" : "s"}
          {offline ? " · mock" : ""}
        </span>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-lg bg-[#DC2626]/10 px-3.5 py-2.5 text-sm font-medium text-[#8f1d1d]"
        >
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-4 text-sm text-muted-ink">Loading versions…</p>
      ) : (
        <div className="mt-4 space-y-2">
          {versions.length === 0 && (
            <p className="text-sm text-muted-ink">
              No versions yet — upload the first one below.
            </p>
          )}
          {versions.map((version) => (
            <div
              key={version.id}
              className="rounded-lg border border-line bg-paper"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <p className="text-sm font-semibold text-charcoal">
                  v{version.version}
                  <span className="ml-2 font-normal text-muted-ink">
                    {version.stats.row_count} rows
                  </span>
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setOpenReport(
                        openReport === version.version ? null : version.version,
                      )
                    }
                    className="inline-flex min-h-[36px] cursor-pointer items-center rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
                    aria-expanded={openReport === version.version}
                  >
                    {openReport === version.version
                      ? "Hide report"
                      : "View report"}
                  </button>
                  <button
                    type="button"
                    disabled={validating !== null || offline}
                    onClick={() => handleValidate(version)}
                    title={
                      offline
                        ? "Revalidation needs the API"
                        : "Recompute the validation report"
                    }
                    className="inline-flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {validating === version.version && (
                      <Loader2
                        className="h-3.5 w-3.5 animate-spin"
                        aria-hidden="true"
                      />
                    )}
                    Revalidate
                  </button>
                </div>
              </div>
              {openReport === version.version && (
                <div className="px-4 pb-4">
                  <ValidationReport report={version.stats} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!offline && (
        <form
          onSubmit={handleUpload}
          className="mt-5 rounded-lg border border-dashed border-line p-4"
          aria-labelledby={`upload-heading-${dataset.id}`}
        >
          <h4
            id={`upload-heading-${dataset.id}`}
            className="font-display text-sm font-bold text-charcoal"
          >
            Upload a new version
          </h4>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_220px]">
            <div>
              <label
                htmlFor={`rows-${dataset.id}`}
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Rows (JSON array)
              </label>
              <textarea
                id={`rows-${dataset.id}`}
                value={rowsText}
                onChange={(e) => setRowsText(e.target.value)}
                rows={5}
                spellCheck={false}
                placeholder='[{"state_summary": "...", "depth": 3, "progress_score": 0.6, "label": "continue"}]'
                className="block w-full rounded-lg border border-line bg-paper px-3.5 py-2.5 font-mono text-sm text-charcoal placeholder:text-muted-ink/70 transition-colors duration-200 focus:border-charcoal"
              />
            </div>
            <div>
              <label
                htmlFor={`label-${dataset.id}`}
                className="mb-1.5 block text-sm font-semibold text-charcoal"
              >
                Label column{" "}
                <span className="font-normal text-muted-ink">(optional)</span>
              </label>
              <input
                id={`label-${dataset.id}`}
                type="text"
                value={labelColumn}
                onChange={(e) => setLabelColumn(e.target.value)}
                placeholder="e.g. label"
                className="block w-full min-h-[44px] rounded-lg border border-line bg-paper px-3.5 text-base text-charcoal placeholder:text-muted-ink/70 transition-colors duration-200 focus:border-charcoal"
              />
              <p className="mt-1.5 text-xs leading-5 text-muted-ink">
                The column with the expected answer, used for class balance and
                leakage checks.
              </p>
            </div>
          </div>
          <button
            type="submit"
            disabled={uploading}
            className="mt-3 inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60"
          >
            {uploading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Upload className="h-4 w-4" aria-hidden="true" />
            )}
            {uploading ? "Uploading…" : "Upload version"}
          </button>
        </form>
      )}
    </article>
  );
}
