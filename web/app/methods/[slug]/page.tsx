import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { TrainingMethod } from "../../../../shared/types";
import { MethodBadges } from "../../../components/MethodBadges";
import { OfflineBanner } from "../../../components/OfflineBanner";
import {
  getMethodDetail,
  isMethodsApiOfflineError,
  type MethodDetailResponse,
  MOCK_METHODS,
  methodCategoryLabel,
  methodCitation,
} from "../../../lib/methods";

export const metadata: Metadata = {
  title: "Method detail",
  description: "Rustenwer training-method detail.",
};

/** Always render on demand: registry data + offline detection must be fresh. */
export const dynamic = "force-dynamic";

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0)
    return <p className="text-sm text-muted-ink">None recorded.</p>;
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-6 text-charcoal">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
        {label}
      </dt>
      <dd className="mt-2">{children}</dd>
    </div>
  );
}

function RequirementRows({
  title,
  entries,
}: {
  title: string;
  entries: Record<string, unknown>;
}) {
  const rows = Object.entries(entries);
  return (
    <div className="rounded-xl border border-line bg-paper p-4">
      <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
        {title}
      </p>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted-ink">None recorded.</p>
      ) : (
        <dl className="mt-3 space-y-2">
          {rows.map(([key, value]) => (
            <div key={key} className="flex justify-between gap-3 text-sm">
              <dt className="font-mono text-[13px] text-muted-ink">{key}</dt>
              <dd className="font-semibold text-charcoal">
                {typeof value === "boolean"
                  ? value
                    ? "yes"
                    : "no"
                  : String(value ?? "—")}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function VersionChip({
  version,
  current,
}: {
  version: TrainingMethod;
  current: number;
}) {
  const isCurrent = version.version === current;
  return (
    <span
      className={`inline-flex min-h-[36px] items-center gap-2 rounded-lg border px-3.5 py-1.5 text-sm font-semibold ${
        isCurrent
          ? "border-charcoal bg-charcoal text-platinum"
          : "border-line bg-card text-charcoal"
      }`}
      title={isCurrent ? "Current version" : `Version ${version.version}`}
    >
      <span className="font-mono">v{version.version}</span>
      {isCurrent && (
        <span className="text-xs font-semibold tracking-wide uppercase opacity-80">
          current
        </span>
      )}
    </span>
  );
}

export default async function MethodDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let detail: MethodDetailResponse | null = null;
  let offline = false;
  try {
    detail = await getMethodDetail(slug);
  } catch (err) {
    if (isMethodsApiOfflineError(err)) {
      offline = true;
      const versions = MOCK_METHODS.filter((m) => m.slug === slug).sort(
        (a, b) => a.version - b.version,
      );
      const current = versions[versions.length - 1];
      detail = current ? { slug, versions, current } : null;
    } else {
      throw err;
    }
  }

  if (!detail) notFound();
  const method = detail.current;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href="/methods"
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All methods
      </Link>

      {offline && (
        <div className="mt-4">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-4 rounded-xl border border-line bg-card p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              {methodCategoryLabel(method.category)} ·{" "}
              <span className="font-mono normal-case">
                {methodCitation(method)}
              </span>
            </p>
            <h1 className="mt-1 font-display text-3xl font-bold tracking-tight text-charcoal">
              {method.name}
            </h1>
            {method.notes && (
              <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
                {method.notes}
              </p>
            )}
          </div>
          <MethodBadges
            status={method.status}
            locallyRunnable={method.locally_runnable}
          />
        </div>

        {detail.versions.length > 1 && (
          <div className="mt-6 border-t border-line pt-6">
            <p className="text-xs font-semibold tracking-wide text-muted-ink uppercase">
              Versions (immutable — a new version is a new record)
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {detail.versions.map((v) => (
                <VersionChip
                  key={v.version}
                  version={v}
                  current={detail.current.version}
                />
              ))}
            </div>
          </div>
        )}

        <dl className="mt-6 grid gap-6 border-t border-line pt-6 sm:grid-cols-2">
          <Field label="Strengths">
            <BulletList items={method.strengths} />
          </Field>
          <Field label="Weaknesses">
            <BulletList items={method.weaknesses} />
          </Field>
          <Field label="Failure modes">
            <BulletList items={method.failure_modes} />
          </Field>
          <Field label="Supported tasks">
            {method.supported_tasks.length === 0 ? (
              <p className="text-sm text-muted-ink">None recorded.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {method.supported_tasks.map((task) => (
                  <span
                    key={task}
                    className="inline-flex min-h-[28px] items-center rounded-full bg-platinum px-3 py-1 text-xs font-semibold text-charcoal"
                  >
                    {task.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            )}
          </Field>
          <Field label="Implementation templates (adapters)">
            {method.implementation_templates.length === 0 ? (
              <p className="text-sm text-muted-ink">
                No adapter registered yet — this method is KNOWN, not locally
                runnable.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {method.implementation_templates.map((template) => (
                  <span
                    key={template}
                    className="inline-flex min-h-[28px] items-center rounded-full bg-charcoal px-3 py-1 font-mono text-xs font-semibold text-platinum"
                  >
                    {template}
                  </span>
                ))}
              </div>
            )}
          </Field>
          <Field label="Compatible architectures">
            <BulletList items={method.compatible_architectures} />
          </Field>
        </dl>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <RequirementRows
            title="Data requirements"
            entries={method.data_requirements}
          />
          <RequirementRows
            title="Compute requirements"
            entries={method.compute_requirements}
          />
        </div>

        <div className="mt-6 border-t border-line pt-6">
          <Field label="Compatible objectives">
            <BulletList items={method.compatible_objectives} />
          </Field>
          <div className="mt-6">
            <Field label="Evaluation requirements">
              <BulletList items={method.evaluation_requirements} />
            </Field>
          </div>
        </div>
      </div>
    </div>
  );
}
