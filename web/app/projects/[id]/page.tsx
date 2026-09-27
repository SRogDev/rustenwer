import {
  ArrowLeft,
  Database,
  Dumbbell,
  FileText,
  Gauge,
  Telescope,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Project } from "../../../../shared/types";
import { OfflineBanner } from "../../../components/OfflineBanner";
import { StatusBadge } from "../../../components/StatusBadge";
import { getProject, isApiOfflineError, MOCK_PROJECTS } from "../../../lib/api";

export const metadata: Metadata = {
  title: "Project detail",
  description: "Rustenwer project detail.",
};

/** Always render on demand: project data + offline detection must be fresh. */
export const dynamic = "force-dynamic";

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const PHASE_ONE_PANELS = [
  {
    icon: FileText,
    title: "Intelligence Specs",
    text: "The formal contract — problem statement, schemas, primitives, and requirements — that every downstream step operates against.",
  },
  {
    icon: Database,
    title: "Datasets",
    text: "Training, validation, and evaluation data attached to this project, with lineage and versioning.",
  },
  {
    icon: Dumbbell,
    title: "Training Jobs",
    text: "Expensive operations run as jobs with a real lifecycle: created, queued, running, completed — or failed honestly.",
  },
  {
    icon: Gauge,
    title: "Evaluations",
    text: "Candidate intelligences measured against your definition of good enough, with comparable scores.",
  },
  {
    icon: Telescope,
    title: "Discovery",
    text: "Observations from production feeding back into the loop: find better candidates, promote what works.",
  },
] as const;

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let project: Project | null = null;
  let offline = false;

  try {
    project = await getProject(id);
  } catch (err) {
    if (isApiOfflineError(err)) {
      offline = true;
      project = MOCK_PROJECTS.find((p) => p.id === id) ?? null;
    } else {
      throw err;
    }
  }

  if (!project) notFound();

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href="/projects"
        className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All projects
      </Link>

      {offline && (
        <div className="mt-4">
          <OfflineBanner />
        </div>
      )}

      <div className="mt-4 rounded-xl border border-line bg-card p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal">
              {project.name}
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
              {project.description ?? "No description yet."}
            </p>
          </div>
          <StatusBadge status={project.status} />
        </div>
        <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-muted-ink">Project ID</dt>
            <dd className="mt-1 font-mono text-[13px] break-all text-charcoal">
              {project.id}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Created</dt>
            <dd className="mt-1 text-charcoal">
              {formatDateTime(project.created_at)}
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-ink">Last updated</dt>
            <dd className="mt-1 text-charcoal">
              {formatDateTime(project.updated_at)}
            </dd>
          </div>
        </dl>
      </div>

      <section aria-labelledby="phase1-heading" className="mt-10">
        <h2
          id="phase1-heading"
          className="font-display text-2xl font-bold tracking-tight text-charcoal"
        >
          The fabrication workspace
        </h2>
        <p className="mt-2 max-w-2xl text-base leading-7 text-muted-ink">
          These panels arrive with Phase 1. For now they mark exactly where
          specs, datasets, jobs, evaluations, and discovery will live.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PHASE_ONE_PANELS.map((panel) => {
            const Icon = panel.icon;
            return (
              <article
                key={panel.title}
                className="relative rounded-xl border border-dashed border-line bg-platinum/30 p-6"
                aria-label={`${panel.title} — Phase 1`}
              >
                <span className="absolute top-4 right-4 rounded-full bg-charcoal px-2.5 py-1 text-[11px] font-bold tracking-wide text-platinum uppercase">
                  Phase 1
                </span>
                <span
                  className="flex h-11 w-11 items-center justify-center rounded-lg bg-platinum text-charcoal"
                  aria-hidden="true"
                >
                  <Icon className="h-5 w-5" />
                </span>
                <h3 className="mt-4 font-display text-lg font-bold text-charcoal">
                  {panel.title}
                </h3>
                <p className="mt-2 text-sm leading-6 text-muted-ink">
                  {panel.text}
                </p>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
