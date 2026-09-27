import { AlertTriangle } from "lucide-react";
import type { Metadata } from "next";
import { NewProjectForm } from "../../components/NewProjectForm";
import { OfflineBanner } from "../../components/OfflineBanner";
import { ProjectCard } from "../../components/ProjectCard";
import { isApiOfflineError, listProjects, MOCK_PROJECTS } from "../../lib/api";

export const metadata: Metadata = {
  title: "Projects",
  description: "Rustenwer projects — containers for fabricated intelligence.",
};

/** Always render on demand: project data + offline detection must be fresh. */
export const dynamic = "force-dynamic";

export default async function ProjectsPage() {
  let offline = false;
  let projects = MOCK_PROJECTS;
  let error: string | null = null;

  try {
    projects = await listProjects();
  } catch (err) {
    if (isApiOfflineError(err)) {
      offline = true;
      projects = MOCK_PROJECTS;
    } else {
      error = err instanceof Error ? err.message : "Failed to load projects.";
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <div className="max-w-2xl">
        <h1 className="font-display text-3xl font-bold tracking-tight text-charcoal sm:text-4xl">
          Projects
        </h1>
        <p className="mt-3 text-base leading-7 text-muted-ink">
          A project is the container for everything Rustenwer fabricates: the
          problem description, its Intelligence Spec, datasets, training jobs,
          and evaluations.
        </p>
      </div>

      {offline && (
        <div className="mt-6">
          <OfflineBanner />
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="mt-6 flex items-start gap-3 rounded-xl bg-[#DC2626]/10 px-4 py-3"
        >
          <AlertTriangle
            className="mt-0.5 h-5 w-5 shrink-0 text-[#8f1d1d]"
            aria-hidden="true"
          />
          <p className="text-sm font-medium text-[#8f1d1d]">
            Could not load projects: {error}
          </p>
        </div>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_380px]">
        <section aria-labelledby="project-list-heading">
          <h2 id="project-list-heading" className="sr-only">
            Project list
          </h2>
          {projects.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line bg-card p-10 text-center">
              <p className="font-display text-lg font-bold text-charcoal">
                No projects yet
              </p>
              <p className="mt-2 text-sm text-muted-ink">
                Create your first project to start describing a problem.
              </p>
            </div>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2">
              {projects.map((p) => (
                <li key={p.id} className="h-full">
                  <ProjectCard project={p} />
                </li>
              ))}
            </ul>
          )}
        </section>
        <aside aria-label="Create a new project">
          <NewProjectForm />
        </aside>
      </div>
    </div>
  );
}
