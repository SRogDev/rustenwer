import type { QualityVector } from "../../shared/types";

/**
 * Inline SVG radar chart for the four ratio-quality dimensions of a
 * QualityVector (plan §30): task_quality, calibration, robustness,
 * reliability. Hand-rolled — no chart dependencies, same SVG style as
 * RunMetricsPanel (charcoal ink on platinum, text labels, role="img").
 * Null dimensions render at the center and are labeled "n/a".
 */
const AXES: { key: keyof QualityVector; label: string }[] = [
  { key: "task_quality", label: "Task quality" },
  { key: "calibration", label: "Calibration" },
  { key: "robustness", label: "Robustness" },
  { key: "reliability", label: "Reliability" },
];

const W = 360;
const H = 320;
const CX = 180;
const CY = 160;
const RADIUS = 100;
const RINGS = [0.25, 0.5, 0.75, 1];

function polar(fraction: number, value: number): [number, number] {
  const angle = -Math.PI / 2 + fraction * 2 * Math.PI;
  return [
    CX + Math.cos(angle) * RADIUS * value,
    CY + Math.sin(angle) * RADIUS * value,
  ];
}

function ringPoints(level: number): string {
  return AXES.map((_, i) => {
    const [x, y] = polar(i / AXES.length, level);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

export function QualityVectorRadar({ vector }: { vector: QualityVector }) {
  const values = AXES.map((axis) => {
    const raw = vector[axis.key];
    return typeof raw === "number" ? Math.min(Math.max(raw, 0), 1) : null;
  });

  const dataPoints = values
    .map((v, i) => {
      const [x, y] = polar(i / values.length, v ?? 0);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const axisLabel = values.every((v) => v === null)
    ? "quality vector — no ratio metrics measured"
    : `quality vector: ${AXES.map((axis, i) =>
        values[i] === null
          ? `${axis.label} n/a`
          : `${axis.label} ${values[i]?.toFixed(2)}`,
      ).join(", ")}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={axisLabel}
      className="h-auto w-full max-w-[380px]"
    >
      {RINGS.map((level) => (
        <polygon
          key={level}
          points={ringPoints(level)}
          fill="none"
          stroke="#d9d7d3"
          strokeWidth={1}
        />
      ))}
      {AXES.map((axis, i) => {
        const [ex, ey] = polar(i / AXES.length, 1);
        const [lx, ly] = polar(i / AXES.length, 1.22);
        const value: number | null = values[i] ?? null;
        return (
          <g key={axis.key}>
            <line
              x1={CX}
              y1={CY}
              x2={ex.toFixed(1)}
              y2={ey.toFixed(1)}
              stroke="#d9d7d3"
              strokeWidth={1}
            />
            <text
              x={lx.toFixed(1)}
              y={ly.toFixed(1)}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={12}
              fontWeight={600}
              fill="#4b4b52"
            >
              {axis.label}
            </text>
            <text
              x={(ex + (lx - ex) * 0.45).toFixed(1)}
              y={(ey + (ly - ey) * 0.45).toFixed(1)}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={11}
              fill="#16161a"
              fontWeight={700}
            >
              {value === null ? "n/a" : value.toFixed(2)}
            </text>
          </g>
        );
      })}
      <polygon
        points={dataPoints}
        fill="rgba(22, 22, 26, 0.12)"
        stroke="#16161a"
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {values.map((v, i) => {
        const [x, y] = polar(i / values.length, v ?? 0);
        return (
          <circle
            key={AXES[i]?.key ?? i}
            cx={x.toFixed(1)}
            cy={y.toFixed(1)}
            r={3.5}
            fill="#16161a"
          />
        );
      })}
    </svg>
  );
}
