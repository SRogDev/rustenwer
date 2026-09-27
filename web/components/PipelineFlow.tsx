import {
  Dumbbell,
  FileText,
  Gauge,
  RefreshCcw,
  Rocket,
  Sparkles,
  Stethoscope,
} from "lucide-react";

/**
 * Static visualization of the Rustenwer fabrication flow:
 * Create Intelligence → Describe → Diagnose → Train → Evaluate → Deploy → Improve.
 * Built with semantic HTML + lucide icons; no JS required, responsive, and
 * motion-free so it respects prefers-reduced-motion by default.
 */
const STEPS = [
  {
    icon: Sparkles,
    title: "Create Intelligence",
    text: "State the problem that needs intelligent behavior — in your own words.",
  },
  {
    icon: FileText,
    title: "Describe",
    text: "The problem becomes an Intelligence Spec: inputs, outputs, and constraints.",
  },
  {
    icon: Stethoscope,
    title: "Diagnose",
    text: "Rustenwer probes the problem's structure and available data before spending a cent.",
  },
  {
    icon: Dumbbell,
    title: "Train",
    text: "Candidate intelligences are built — from rules to small models — ranked by cost.",
  },
  {
    icon: Gauge,
    title: "Evaluate",
    text: "Candidates prove themselves against your definition of good enough.",
  },
  {
    icon: Rocket,
    title: "Deploy",
    text: "The winner ships as a durable, observable artifact — not a notebook.",
  },
  {
    icon: RefreshCcw,
    title: "Improve",
    text: "Production observations feed the next loop: fabricate, compare, promote.",
  },
] as const;

export function PipelineFlow() {
  return (
    <ol
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      aria-label="The intelligence fabrication flow"
    >
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const isLast = i === STEPS.length - 1;
        return (
          <li
            key={step.title}
            className={`relative rounded-xl border border-line bg-card p-5 ${isLast ? "sm:col-span-2 lg:col-span-1 xl:col-span-1" : ""}`}
          >
            <div className="flex items-center gap-3">
              <span
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-platinum text-charcoal"
                aria-hidden="true"
              >
                <Icon className="h-5 w-5" />
              </span>
              <div className="flex items-baseline gap-2">
                <span
                  className="font-mono text-xs font-semibold text-muted-ink"
                  aria-hidden="true"
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="font-display text-base font-bold text-charcoal">
                  {step.title}
                </h3>
              </div>
            </div>
            <p className="mt-3 text-sm leading-6 text-muted-ink">{step.text}</p>
            <span className="sr-only">
              {`Step ${i + 1} of ${STEPS.length}${isLast ? " (final)" : ", then"}`}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
