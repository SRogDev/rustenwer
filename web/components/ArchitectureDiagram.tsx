import { ArrowDown } from "lucide-react";
import type {
  ArchitectureComponent,
  IntelligenceArchitecture,
} from "../../shared/types";
import { StatusPill } from "./StatusPill";

/** One-line human summary of a component's config for the diagram card. */
function configSummary(config: Record<string, unknown>): string[] {
  const entries = Object.entries(config).slice(0, 4);
  return entries.map(([key, value]) => {
    const rendered =
      typeof value === "object" ? JSON.stringify(value) : String(value);
    return `${key}: ${rendered}`;
  });
}

function ArchitectureComponentCard({
  component,
  index,
}: {
  component: ArchitectureComponent;
  index: number;
}) {
  return (
    <div className="rounded-xl border border-line bg-paper p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-platinum font-mono text-xs font-bold text-charcoal">
          {index + 1}
        </span>
        <StatusPill status={component.kind.replace(/_/g, " ")} />
        {component.label && (
          <span className="text-sm font-semibold text-charcoal">
            {component.label}
          </span>
        )}
      </div>
      {component.ref && (
        <p className="mt-2 font-mono text-xs break-all text-muted-ink">
          pinned ref: {component.ref}
        </p>
      )}
      {Object.keys(component.config).length > 0 && (
        <dl className="mt-2 space-y-1">
          {configSummary(component.config).map((line) => (
            <div key={line} className="font-mono text-xs text-muted-ink">
              {line}
            </div>
          ))}
          {Object.keys(component.config).length > 4 && (
            <div className="font-mono text-xs text-muted-ink">…</div>
          )}
        </dl>
      )}
    </div>
  );
}

/**
 * Renders an immutable architecture snapshot as an execution pipeline:
 * components in execution order, each card pinned to its immutable ref.
 * Pure server component — no client state.
 */
export function ArchitectureDiagram({
  architecture,
}: {
  architecture: IntelligenceArchitecture | null;
}) {
  if (!architecture || architecture.components.length === 0) {
    return (
      <p className="text-sm text-muted-ink">
        No architecture snapshot recorded for this version.
      </p>
    );
  }
  const order = architecture.execution_order.length
    ? architecture.execution_order
    : architecture.components.map((_, i) => i);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={architecture.kind.replace(/_/g, " ")} />
        <span className="text-xs text-muted-ink">
          {order.length} component{order.length === 1 ? "" : "s"} · immutable
          snapshot
        </span>
      </div>
      <ol className="mt-4 space-y-0">
        {order.map((componentIndex, position) => {
          const component = architecture.components[componentIndex];
          if (!component) return null;
          const isLast = position === order.length - 1;
          return (
            <li key={componentIndex}>
              <ArchitectureComponentCard
                component={component}
                index={componentIndex}
              />
              {!isLast && (
                <div className="flex justify-center py-1.5" aria-hidden="true">
                  <ArrowDown className="h-4 w-4 text-muted-ink" />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
