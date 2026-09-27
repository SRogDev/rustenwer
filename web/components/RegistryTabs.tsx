"use client";

import { ArrowRight, Boxes, BrainCircuit, FlaskConical } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { Benchmark, Intelligence, Model } from "../../shared/types";
import { BenchmarkCreateForm } from "./BenchmarkCreateForm";
import { IntelligenceCreateForm } from "./IntelligenceCreateForm";
import { StatusPill } from "./StatusPill";

type Tab = "models" | "intelligences" | "benchmarks";

const TABS: { id: Tab; label: string }[] = [
  { id: "models", label: "Models" },
  { id: "intelligences", label: "Intelligences" },
  { id: "benchmarks", label: "Benchmarks" },
];

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-card p-8 text-center">
      <p className="text-sm text-muted-ink">{text}</p>
    </div>
  );
}

const CARD_LINK =
  "block h-full rounded-xl border border-line bg-card p-5 transition-all duration-200 hover:border-charcoal hover:shadow-[0_4px_6px_rgba(0,0,0,0.1)]";

/**
 * Registry browser with three tabs: Models, Intelligences, Benchmarks.
 * Lists are fetched server-side (with the offline mock fallback); the tabs
 * and the create forms are client-side.
 */
export function RegistryTabs({
  projectId,
  models,
  intelligences,
  benchmarks,
}: {
  projectId: string;
  models: Model[];
  intelligences: Intelligence[];
  benchmarks: Benchmark[];
}) {
  const [tab, setTab] = useState<Tab>("models");

  return (
    <div>
      <div
        role="tablist"
        aria-label="Registry sections"
        className="inline-flex rounded-xl border border-line bg-card p-1"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`min-h-[44px] cursor-pointer rounded-lg px-4 py-2 text-sm font-semibold transition-colors duration-200 ${
              tab === t.id
                ? "bg-charcoal text-platinum"
                : "text-charcoal hover:bg-platinum"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "models" && (
        <div role="tabpanel" aria-label="Models" className="mt-6">
          {models.length === 0 ? (
            <EmptyState text="No models yet. Train a candidate to register its first model here." />
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2">
              {models.map((model) => (
                <li key={model.id}>
                  <Link
                    href={`/projects/${projectId}/registry/models/${model.id}`}
                    className={CARD_LINK}
                  >
                    <div className="flex items-start gap-3">
                      <Boxes
                        className="mt-0.5 h-5 w-5 shrink-0 text-charcoal"
                        aria-hidden="true"
                      />
                      <div>
                        <h3 className="font-display text-lg font-bold text-charcoal">
                          {model.name}
                        </h3>
                        <p className="mt-1 line-clamp-2 text-sm leading-6 text-muted-ink">
                          {model.description ?? "No description yet."}
                        </p>
                        <p className="mt-3 text-xs font-semibold tracking-wide text-muted-ink uppercase">
                          Registered {formatDateTime(model.created_at)}
                        </p>
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "intelligences" && (
        <div
          role="tabpanel"
          aria-label="Intelligences"
          className="mt-6 space-y-6"
        >
          <IntelligenceCreateForm projectId={projectId} />
          {intelligences.length === 0 ? (
            <EmptyState text="No intelligences yet. Create one above to start packaging models into executable systems." />
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2">
              {intelligences.map((intelligence) => (
                <li key={intelligence.id}>
                  <Link
                    href={`/projects/${projectId}/registry/intelligences/${intelligence.id}`}
                    className={CARD_LINK}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3">
                        <BrainCircuit
                          className="mt-0.5 h-5 w-5 shrink-0 text-charcoal"
                          aria-hidden="true"
                        />
                        <div>
                          <h3 className="font-display text-lg font-bold text-charcoal">
                            {intelligence.name}
                          </h3>
                          <p className="mt-1 line-clamp-2 text-sm leading-6 text-muted-ink">
                            {intelligence.description ?? "No description yet."}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
                        Primitive:{" "}
                        {intelligence.primitive?.replace(/_/g, " ") ?? "none"}
                      </p>
                      <ArrowRight
                        className="h-4 w-4 shrink-0 text-muted-ink"
                        aria-hidden="true"
                      />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "benchmarks" && (
        <div role="tabpanel" aria-label="Benchmarks" className="mt-6 space-y-6">
          <BenchmarkCreateForm projectId={projectId} />
          {benchmarks.length === 0 ? (
            <EmptyState text="No benchmarks yet. Create one above, or use the seeded termination benchmark." />
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2">
              {benchmarks.map((benchmark) => (
                <li key={benchmark.id}>
                  <Link
                    href={`/projects/${projectId}/registry/benchmarks/${benchmark.id}`}
                    className={CARD_LINK}
                  >
                    <div className="flex items-start gap-3">
                      <FlaskConical
                        className="mt-0.5 h-5 w-5 shrink-0 text-charcoal"
                        aria-hidden="true"
                      />
                      <div>
                        <h3 className="font-display text-lg font-bold text-charcoal">
                          {benchmark.name}
                        </h3>
                        <p className="mt-1 line-clamp-2 text-sm leading-6 text-muted-ink">
                          {benchmark.description}
                        </p>
                        {benchmark.metrics.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {benchmark.metrics.slice(0, 4).map((metric) => (
                              <StatusPill key={metric} status={metric} />
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
