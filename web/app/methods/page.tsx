import { ArrowRight, FlaskConical } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type {
  MethodCategory,
  MethodValidationStatus,
  ResearchFinding,
  TrainingMethod,
} from "../../../shared/types";
import { MethodBadges } from "../../components/MethodBadges";
import { OfflineBanner } from "../../components/OfflineBanner";
import {
  isMethodsApiOfflineError,
  listMethods,
  listResearchFindings,
  METHOD_CATEGORIES,
  MOCK_METHODS,
  MOCK_RESEARCH_FINDINGS,
  methodCategoryLabel,
  methodCitation,
} from "../../lib/methods";

export const metadata: Metadata = {
  title: "Training methods",
  description:
    "Rustenwer training-method catalog: the §10 taxonomy, validated vs known.",
};

/** Always render on demand: catalog + offline detection must be fresh. */
export const dynamic = "force-dynamic";

async function withOffline<T>(
  fetch: () => Promise<T>,
  mock: T,
): Promise<{ data: T; offline: boolean }> {
  try {
    return { data: await fetch(), offline: false };
  } catch (err) {
    if (isMethodsApiOfflineError(err)) return { data: mock, offline: true };
    throw err;
  }
}

function FilterLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`inline-flex min-h-[36px] items-center rounded-full px-3.5 py-1.5 text-xs font-semibold tracking-wide transition-colors duration-200 ${
        active
          ? "bg-charcoal text-platinum"
          : "bg-platinum text-charcoal hover:bg-platinum-deep"
      }`}
    >
      {children}
    </Link>
  );
}

function MethodCard({ method }: { method: TrainingMethod }) {
  return (
    <li>
      <Link
        href={`/methods/${method.slug}`}
        className="block h-full rounded-xl border border-line bg-card p-5 transition-all duration-200 hover:border-charcoal hover:shadow-[0_4px_6px_rgba(0,0,0,0.1)]"
        aria-label={`View ${method.name} details`}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-display text-lg font-bold text-charcoal">
              {method.name}
            </h3>
            <p className="mt-0.5 font-mono text-xs text-muted-ink">
              {methodCitation(method)}
            </p>
          </div>
          <MethodBadges
            status={method.status}
            locallyRunnable={method.locally_runnable}
          />
        </div>
        <p className="mt-2 text-xs font-semibold tracking-wide text-muted-ink uppercase">
          {methodCategoryLabel(method.category)}
        </p>
        {method.strengths.length > 0 && (
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-ink">
            {method.strengths[0]}
          </p>
        )}
      </Link>
    </li>
  );
}

function ResearchSection({ findings }: { findings: ResearchFinding[] }) {
  if (findings.length === 0) return null;
  return (
    <section aria-labelledby="research-heading" className="mt-12">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-5 w-5 text-charcoal" aria-hidden="true" />
        <h2
          id="research-heading"
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          Research knowledge
        </h2>
      </div>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-ink">
        Distilled technique findings (plan §52). Each finding records what a
        technique is useful for, what it requires, its advantage, and its
        weakness.
      </p>
      <ul className="mt-4 grid gap-4 sm:grid-cols-2">
        {findings.map((finding) => (
          <li
            key={finding.technique}
            className="rounded-xl border border-line bg-card p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-display text-base font-bold text-charcoal">
                {finding.technique}
              </h3>
              <span className="shrink-0 font-mono text-xs text-muted-ink">
                v{finding.version}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-charcoal">
              <span className="font-semibold">Advantage: </span>
              {finding.advantage}
            </p>
            <p className="mt-1.5 text-sm leading-6 text-muted-ink">
              <span className="font-semibold text-charcoal">Weakness: </span>
              {finding.weakness}
            </p>
            <dl className="mt-3 space-y-1.5 border-t border-line pt-3 text-sm">
              <div className="flex gap-2">
                <dt className="shrink-0 font-semibold text-muted-ink">
                  Useful for
                </dt>
                <dd className="text-charcoal">
                  {finding.useful_for.join("; ")}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0 font-semibold text-muted-ink">
                  Requires
                </dt>
                <dd className="text-charcoal">{finding.requires.join("; ")}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0 font-semibold text-muted-ink">
                  Source
                </dt>
                <dd className="font-mono text-xs text-charcoal">
                  {finding.source}
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function MethodsPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; status?: string }>;
}) {
  const { category, status } = await searchParams;

  const [methodsResult, researchResult] = await Promise.all([
    withOffline(
      () =>
        listMethods({
          category: category as MethodCategory | undefined,
          status: status as MethodValidationStatus | undefined,
        }),
      // Mock: apply the same filters locally so offline behaves identically.
      MOCK_METHODS.filter(
        (m) =>
          (!category || m.category === category) &&
          (!status || m.status === status),
      ),
    ),
    withOffline(() => listResearchFindings(), MOCK_RESEARCH_FINDINGS),
  ]);

  const offline = methodsResult.offline || researchResult.offline;
  const methods: TrainingMethod[] = methodsResult.data;
  const findings: ResearchFinding[] = researchResult.data;

  const counts = new Map<MethodCategory, number>();
  for (const m of methodsResult.data) {
    counts.set(m.category, (counts.get(m.category) ?? 0) + 1);
  }

  const statusOptions: Array<"all" | MethodValidationStatus> = [
    "all",
    "VALIDATED",
    "KNOWN",
  ];

  function categoryHref(next: string | null): string {
    const params = new URLSearchParams();
    if (next) params.set("category", next);
    if (status) params.set("status", status);
    const qs = params.toString();
    return `/methods${qs ? `?${qs}` : ""}`;
  }

  function statusHref(next: "all" | MethodValidationStatus): string {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (next !== "all") params.set("status", next);
    const qs = params.toString();
    return `/methods${qs ? `?${qs}` : ""}`;
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      {offline && (
        <div className="mb-4">
          <OfflineBanner />
        </div>
      )}

      <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
        Training methods
      </h1>
      <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
        The §10 taxonomy as versioned, structured knowledge (plan §11).
        <span className="font-semibold text-charcoal"> VALIDATED</span> methods
        have a real local or GPU run behind them;{" "}
        <span className="font-semibold text-charcoal">KNOWN</span> entries are
        honest taxonomy placeholders — no adapter yet. The recommendation engine
        queries this registry instead of hardcoding a method branch.
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[240px_1fr]">
        <nav
          aria-label="Method taxonomy"
          className="lg:sticky lg:top-24 lg:self-start"
        >
          <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Taxonomy (§10)
          </p>
          <ul className="mt-3 space-y-1">
            <li>
              <Link
                href={categoryHref(null)}
                aria-current={!category ? "page" : undefined}
                className={`flex min-h-[44px] items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors duration-200 ${
                  !category
                    ? "bg-charcoal text-platinum"
                    : "text-charcoal hover:bg-platinum"
                }`}
              >
                All categories
                <span className="font-mono text-xs opacity-70">
                  {methodsResult.data.length}
                </span>
              </Link>
            </li>
            {METHOD_CATEGORIES.map((cat) => {
              const active = category === cat;
              return (
                <li key={cat}>
                  <Link
                    href={categoryHref(cat)}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-[44px] items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-200 ${
                      active
                        ? "bg-charcoal text-platinum"
                        : "text-charcoal hover:bg-platinum"
                    }`}
                  >
                    {methodCategoryLabel(cat)}
                    <span className="font-mono text-xs opacity-70">
                      {counts.get(cat) ?? 0}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          <p className="mt-6 text-xs font-semibold tracking-wide text-muted-ink uppercase">
            Status
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {statusOptions.map((opt) => (
              <FilterLink
                key={opt}
                href={statusHref(opt)}
                active={(status ?? "all") === opt}
              >
                {opt === "all" ? "All" : opt}
              </FilterLink>
            ))}
          </div>
        </nav>

        <div>
          {methods.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line bg-card p-8 text-center">
              <p className="text-sm text-muted-ink">
                No methods match these filters.
              </p>
            </div>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2">
              {methods.map((method) => (
                <MethodCard key={methodCitation(method)} method={method} />
              ))}
            </ul>
          )}
        </div>
      </div>

      <ResearchSection findings={findings} />

      <div className="mt-10">
        <Link
          href="/projects"
          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
        >
          Back to projects
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
}
