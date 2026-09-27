import type { ProjectStatus } from "../../shared/types";

const STYLES: Record<ProjectStatus, string> = {
  ACTIVE: "bg-charcoal text-platinum",
  PAUSED: "bg-platinum-deep text-charcoal",
  ARCHIVED: "bg-platinum text-muted-ink",
};

export function StatusBadge({ status }: { status: ProjectStatus }) {
  const label =
    status === "ACTIVE"
      ? "Active"
      : status === "PAUSED"
        ? "Paused"
        : "Archived";
  return (
    <span
      className={`inline-flex min-h-[28px] items-center rounded-full px-3 py-1 text-xs font-semibold tracking-wide uppercase ${STYLES[status]}`}
    >
      {label}
    </span>
  );
}
