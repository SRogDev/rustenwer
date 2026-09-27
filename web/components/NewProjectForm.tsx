"use client";

import { Loader2, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createProject, isApiOfflineError } from "../lib/api";

/**
 * New-project form. Posts to the API; while the backend is offline it
 * refuses honestly instead of pretending to create a project.
 */
export function NewProjectForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("A project name is required.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await createProject({
        name: trimmed,
        description: description.trim() || undefined,
      });
      router.refresh();
      setName("");
      setDescription("");
    } catch (err) {
      if (isApiOfflineError(err)) {
        setError(
          "The API is offline, so the project could not be created. Start the backend at http://localhost:8000 and try again.",
        );
      } else {
        setError(
          err instanceof Error ? err.message : "Failed to create project.",
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-line bg-card p-6 shadow-[0_1px_2px_rgba(0,0,0,0.05)]"
      aria-labelledby="new-project-heading"
    >
      <h2
        id="new-project-heading"
        className="font-display text-lg font-bold tracking-tight text-charcoal"
      >
        New project
      </h2>
      <p className="mt-1 text-sm text-muted-ink">
        A project is a container for everything Rustenwer fabricates: specs,
        datasets, training jobs, and evaluations.
      </p>

      <div className="mt-4 space-y-4">
        <div>
          <label
            htmlFor="project-name"
            className="mb-1.5 block text-sm font-semibold text-charcoal"
          >
            Name <span aria-hidden="true">*</span>
          </label>
          <input
            id="project-name"
            name="name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Support triage classifier"
            maxLength={200}
            className="block w-full min-h-[44px] rounded-lg border border-line bg-paper px-3.5 text-base text-charcoal placeholder:text-muted-ink/70 transition-colors duration-200 focus:border-charcoal"
            aria-describedby={error ? "project-form-error" : undefined}
          />
        </div>
        <div>
          <label
            htmlFor="project-description"
            className="mb-1.5 block text-sm font-semibold text-charcoal"
          >
            Description{" "}
            <span className="font-normal text-muted-ink">(optional)</span>
          </label>
          <textarea
            id="project-description"
            name="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What problem should this project's intelligence solve?"
            rows={3}
            maxLength={2000}
            className="block w-full rounded-lg border border-line bg-paper px-3.5 py-2.5 text-base text-charcoal placeholder:text-muted-ink/70 transition-colors duration-200 focus:border-charcoal"
          />
        </div>
      </div>

      {error && (
        <p
          id="project-form-error"
          role="alert"
          className="mt-4 rounded-lg bg-[#DC2626]/10 px-3.5 py-2.5 text-sm font-medium text-[#8f1d1d]"
        >
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="mt-4 inline-flex min-h-[44px] min-w-[44px] cursor-pointer items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Plus className="h-4 w-4" aria-hidden="true" />
        )}
        {pending ? "Creating…" : "Create project"}
      </button>
    </form>
  );
}
