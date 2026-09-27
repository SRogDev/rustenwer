import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { Dataset } from "../../../../../shared/types";
import { DatasetCard } from "../../../../components/DatasetCard";
import { DatasetCreateForm } from "../../../../components/DatasetCreateForm";
import { OfflineBanner } from "../../../../components/OfflineBanner";
import {
  isApiOfflineError,
  listDatasets,
  MOCK_DATASETS,
} from "../../../../lib/api";

export const metadata: Metadata = {
  title: "Datasets",
  description: "Rustenwer datasets — training data with validation lineage.",
};

/** Always render on demand: dataset data + offline detection must be fresh. */
export const dynamic = "force-dynamic";

export default async function DatasetsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let datasets: Dataset[] = [];
  let offline = false;

  try {
    datasets = await listDatasets(id);
  } catch (err) {
    if (isApiOfflineError(err)) {
      offline = true;
      datasets = MOCK_DATASETS;
    } else {
      throw err;
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/projects/${id}`}
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to project
      </Link>

      <div className="mt-4 max-w-2xl">
        <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
          Datasets
        </h1>
        <p className="mt-3 text-base leading-7 text-muted-ink">
          Training, validation, and evaluation data attached to this project.
          Every version is validated deterministically — column schema, class
          balance, leakage flags, and a recommended split — before it can train
          anything.
        </p>
      </div>

      {offline && (
        <div className="mt-6">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_380px]">
        <section aria-labelledby="dataset-list-heading" className="space-y-6">
          <h2 id="dataset-list-heading" className="sr-only">
            Dataset list
          </h2>
          {datasets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line bg-card p-10 text-center">
              <p className="font-display text-lg font-bold text-charcoal">
                No datasets yet
              </p>
              <p className="mt-2 text-sm text-muted-ink">
                Create your first dataset, then upload a version of labeled
                rows.
              </p>
            </div>
          ) : (
            datasets.map((dataset) => (
              <DatasetCard key={dataset.id} dataset={dataset} />
            ))
          )}
        </section>
        <aside aria-label="Create a new dataset">
          <DatasetCreateForm projectId={id} />
        </aside>
      </div>
    </div>
  );
}
