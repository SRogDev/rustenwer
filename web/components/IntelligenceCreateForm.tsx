"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { IntelligencePrimitive } from "../../shared/types";
import { INTELLIGENCE_PRIMITIVES } from "../../shared/types";
import { createIntelligence, isApiOfflineError } from "../lib/api";
import {
  BUTTON_PRIMARY,
  ERROR_STYLES,
  HINT_STYLES,
  INPUT_STYLES,
  LABEL_STYLES,
} from "./formStyles";

/**
 * Create-intelligence form (Phase 3 registry).
 * Fields: name, description, primitive select. On success the page
 * refreshes so the new intelligence appears in the list.
 */
export function IntelligenceCreateForm({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [primitive, setPrimitive] = useState<IntelligencePrimitive | "">("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim().length > 0 && !saving;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      await createIntelligence(projectId, {
        name: name.trim(),
        description: description.trim() === "" ? undefined : description.trim(),
        primitive: primitive === "" ? null : primitive,
      });
      setName("");
      setDescription("");
      setPrimitive("");
      router.refresh();
    } catch (err) {
      setError(
        isApiOfflineError(err)
          ? "The API is offline, so the intelligence cannot be created."
          : err instanceof Error
            ? err.message
            : "Could not create the intelligence.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-line bg-card p-5"
    >
      <h3 className="font-display text-base font-bold text-charcoal">
        New intelligence
      </h3>
      <p className="mt-1 text-sm text-muted-ink">
        An intelligence is an executable cognitive system — separate from the
        models it may be composed of.
      </p>

      {error && (
        <p role="alert" className={`${ERROR_STYLES} mt-4`}>
          {error}
        </p>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="intelligence-name" className={LABEL_STYLES}>
            Name
          </label>
          <input
            id="intelligence-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="search-termination"
            className={INPUT_STYLES}
          />
        </div>
        <div>
          <label htmlFor="intelligence-primitive" className={LABEL_STYLES}>
            Primitive
          </label>
          <select
            id="intelligence-primitive"
            value={primitive}
            onChange={(e) =>
              setPrimitive(e.target.value as IntelligencePrimitive | "")
            }
            className={INPUT_STYLES}
          >
            <option value="">None yet</option>
            {INTELLIGENCE_PRIMITIVES.map((p) => (
              <option key={p} value={p}>
                {p.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <p className={HINT_STYLES}>Optional at creation time.</p>
        </div>
      </div>

      <div className="mt-4">
        <label htmlFor="intelligence-description" className={LABEL_STYLES}>
          Description
        </label>
        <textarea
          id="intelligence-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="What does this intelligence do?"
          className={INPUT_STYLES}
        />
      </div>

      <div className="mt-4">
        <button type="submit" disabled={!canSubmit} className={BUTTON_PRIMARY}>
          {saving && (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          {saving ? "Creating…" : "Create intelligence"}
        </button>
      </div>
    </form>
  );
}
