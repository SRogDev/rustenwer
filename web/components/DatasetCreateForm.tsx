"use client";

import { Loader2, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createDataset, isApiOfflineError } from "../lib/api";

/**
 * Dataset creation form. Refuses honestly while the API is offline instead
 * of pretending to create a dataset.
 */
export function DatasetCreateForm({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("A dataset name is required.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await createDataset(projectId, {
        name: trimmed,
        description: description.trim() || undefined,
      });
      setName("");
      setDescription("");
      router.refresh();
    } catch (err) {
      if (isApiOfflineError(err)) {
        setError(
          "The API is offline, so the dataset could not be created. Start the backend at http://localhost:8000 and try again.",
        );
      } else {
        setError(
          err instanceof Error ? err.message : "Failed to create dataset.",
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-line bg-card p-6"
      aria-labelledby="new-dataset-heading"
    >
      <h2
        id="new-dataset-heading"
        className="font-display text-lg font-bold tracking-tight text-charcoal"
      >
        New dataset
      </h2>
      <p className="mt-1 text-sm leading-6 text-muted-ink">
        A named collection of examples. Upload versions of rows next, and
        Rustenwer validates each one deterministically.
      </p>
      <div className="mt-4 space-y-4">
        <div>
          <label
            htmlFor="dataset-name"
            className="mb-1.5 block text-sm font-semibold text-charcoal"
          >
            Name <span aria-hidden="true">*</span>
          </label>
          <input
            id="dataset-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. termination demo dataset"
            maxLength={200}
            className="block w-full min-h-[44px] rounded-lg border border-line bg-paper px-3.5 text-base text-charcoal placeholder:text-muted-ink/70 transition-colors duration-200 focus:border-charcoal"
          />
        </div>
        <div>
          <label
            htmlFor="dataset-description"
            className="mb-1.5 block text-sm font-semibold text-charcoal"
          >
            Description{" "}
            <span className="font-normal text-muted-ink">(optional)</span>
          </label>
          <textarea
            id="dataset-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            maxLength={2000}
            placeholder="What do these examples represent?"
            className="block w-full rounded-lg border border-line bg-paper px-3.5 py-2.5 text-base text-charcoal placeholder:text-muted-ink/70 transition-colors duration-200 focus:border-charcoal"
          />
        </div>
      </div>
      {error && (
        <p
          role="alert"
          className="mt-4 rounded-lg bg-[#DC2626]/10 px-3.5 py-2.5 text-sm font-medium text-[#8f1d1d]"
        >
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="mt-4 inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Plus className="h-4 w-4" aria-hidden="true" />
        )}
        {pending ? "Creating…" : "Create dataset"}
      </button>
    </form>
  );
}
