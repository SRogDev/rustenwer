import { ArrowRight } from "lucide-react";
import Link from "next/link";
import type { Project } from "../../shared/types";
import { StatusBadge } from "./StatusBadge";

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function ProjectCard({ project }: { project: Project }) {
  return (
    <article className="flex h-full flex-col rounded-xl border border-line bg-card p-6 shadow-[0_1px_2px_rgba(0,0,0,0.05)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_15px_rgba(0,0,0,0.1)]">
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-display text-lg font-bold tracking-tight text-charcoal">
          <Link
            href={`/projects/${project.id}`}
            className="rounded-md transition-colors duration-200 hover:text-charcoal-soft hover:underline"
          >
            {project.name}
          </Link>
        </h2>
        <StatusBadge status={project.status} />
      </div>
      <p className="mt-2 flex-1 text-sm leading-6 text-muted-ink">
        {project.description ?? "No description yet."}
      </p>
      <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
        <p className="text-xs text-muted-ink">
          Created {formatDate(project.created_at)}
        </p>
        <Link
          href={`/projects/${project.id}`}
          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md px-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:bg-platinum"
          aria-label={`Open ${project.name}`}
        >
          Open
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}
