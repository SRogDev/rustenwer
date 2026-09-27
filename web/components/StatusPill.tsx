/**
 * Generic status pill for Phase-1 entity statuses (specs, jobs, evaluations,
 * deployments, dataset versions). Tones stay inside the platinum theme.
 */
const TONES: Record<string, string> = {
  DRAFT: "bg-platinum text-muted-ink",
  ARCHIVED: "bg-platinum text-muted-ink",
  CANCELLED: "bg-platinum text-muted-ink",
  PAUSED: "bg-platinum text-muted-ink",
  PENDING: "bg-platinum text-muted-ink",
  CREATED: "bg-platinum-deep text-charcoal",
  QUEUED: "bg-platinum-deep text-charcoal",
  DIAGNOSED: "bg-platinum-deep text-charcoal",
  RUNNING: "bg-charcoal text-platinum",
  APPROVED: "bg-charcoal text-platinum",
  COMPLETED: "bg-charcoal text-platinum",
  ACTIVE: "bg-charcoal text-platinum",
  FAILED: "bg-[#DC2626]/10 text-[#8f1d1d]",
};

export function StatusPill({ status }: { status: string }) {
  const tone = TONES[status] ?? "bg-platinum text-muted-ink";
  const label = status
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase());
  return (
    <span
      className={`inline-flex min-h-[28px] items-center rounded-full px-3 py-1 text-xs font-semibold tracking-wide uppercase ${tone}`}
    >
      {label}
    </span>
  );
}
