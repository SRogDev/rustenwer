import {
  ArrowDownWideNarrow,
  Crosshair,
  GitBranch,
  ShieldCheck,
  Tags,
  Telescope,
} from "lucide-react";

/**
 * Feature cards for the Intelligence Primitive concept (plan §2.3).
 * Primitives are the reusable cognitive operations Rustenwer composes
 * instead of hand-building one-off models.
 */
const PRIMITIVES = [
  {
    icon: GitBranch,
    name: "decision",
    text: "Choose between options under uncertainty — the atom of every intelligent system.",
  },
  {
    icon: Tags,
    name: "classification",
    text: "Assign inputs to categories with measured confidence, not vibes.",
  },
  {
    icon: ArrowDownWideNarrow,
    name: "ranking",
    text: "Order candidates by expected value so the best one wins every time.",
  },
  {
    icon: Crosshair,
    name: "prediction",
    text: "Estimate what happens next from what happened before — with error bars.",
  },
  {
    icon: Telescope,
    name: "anomaly_detection",
    text: "Spot the inputs that break the pattern before they break production.",
  },
  {
    icon: ShieldCheck,
    name: "verification",
    text: "Check an answer against constraints independently of whoever produced it.",
  },
] as const;

export function PrimitiveCards() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {PRIMITIVES.map((p) => {
        const Icon = p.icon;
        return (
          <article
            key={p.name}
            className="rounded-xl border border-line bg-card p-5 shadow-[0_1px_2px_rgba(0,0,0,0.05)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_15px_rgba(0,0,0,0.1)]"
          >
            <span
              className="flex h-11 w-11 items-center justify-center rounded-lg bg-charcoal text-platinum"
              aria-hidden="true"
            >
              <Icon className="h-5 w-5" />
            </span>
            <h3 className="mt-4 font-mono text-sm font-bold text-charcoal">
              {p.name}
            </h3>
            <p className="mt-2 text-sm leading-6 text-muted-ink">{p.text}</p>
          </article>
        );
      })}
    </div>
  );
}
