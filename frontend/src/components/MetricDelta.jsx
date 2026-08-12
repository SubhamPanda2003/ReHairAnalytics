import { Minus, TrendingDown, TrendingUp } from "lucide-react";

/**
 * Standard "baseline -> current -> change" line used under every score in the app.
 * `noiseFloor`, when given, is this reading's own measured (or default) noise
 * floor -- a delta smaller than that is shown as neutral/muted rather than a
 * colored up/down arrow, since it isn't distinguishable from normal AI scoring
 * noise and shouldn't read as confirmed progress or regression.
 */
export default function MetricDelta({ current, baseline, testId, emptyLabel = "This is your baseline", noiseFloor }) {
  if (baseline === null || baseline === undefined || current === null || current === undefined) {
    return <p className="text-[11px] text-muted-foreground mt-1.5" data-testid={testId}>{emptyLabel}</p>;
  }
  const delta = Math.round((current - baseline) * 10) / 10;
  const withinNoise = noiseFloor != null && Math.abs(delta) < noiseFloor;
  const Icon = withinNoise ? Minus : delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
  const cls = withinNoise ? "text-muted-foreground" : delta > 0 ? "text-primary" : delta < 0 ? "text-destructive" : "text-muted-foreground";
  return (
    <p className="text-[11px] text-muted-foreground mt-1.5 flex items-center gap-1" data-testid={testId}>
      Baseline {Math.round(baseline)}
      <span className={`inline-flex items-center gap-0.5 font-semibold ${cls}`}>
        <Icon className="w-3 h-3" />{delta > 0 ? "+" : ""}{delta}
      </span>
      {withinNoise && <span className="italic font-normal">(within normal variation)</span>}
    </p>
  );
}
