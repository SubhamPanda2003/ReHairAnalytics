import React from "react";

export default function ScoreRing({ value = 0, size = 120, stroke = 10, label, color = "hsl(var(--chart-1))", testId }) {
  const hasValue = value !== null && value !== undefined;
  const radius = (size - stroke) / 2;
  const circ = 2 * Math.PI * radius;
  const offset = circ - (hasValue ? Math.max(0, Math.min(100, value)) / 100 : 0) * circ;
  return (
    <div className="relative inline-flex items-center justify-center" data-testid={testId}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} />
        {hasValue && (
          <circle
            cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={stroke}
            strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
          />
        )}
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-heading text-2xl font-bold">{hasValue ? Math.round(value) : "—"}</span>
        {label && <span className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mt-0.5">{label}</span>}
      </div>
    </div>
  );
}
