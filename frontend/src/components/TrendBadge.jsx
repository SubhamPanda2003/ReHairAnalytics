import { TrendingUp, TrendingDown, MinusCircle, HelpCircle, AlertTriangle } from "lucide-react";

// Mirrors backend utils/trend.py's fit_trend() "direction" values.
const CONFIG = {
  improving: { icon: TrendingUp, cls: "bg-primary/15 text-primary", label: "Confirmed improving" },
  declining: { icon: TrendingDown, cls: "bg-destructive/15 text-destructive", label: "Confirmed declining" },
  flat_or_unconfirmed: { icon: MinusCircle, cls: "bg-muted text-muted-foreground", label: "No confirmed trend yet" },
  insufficient_data: { icon: HelpCircle, cls: "bg-muted text-muted-foreground", label: "Not enough scans yet" },
};

/** Whether the score is REALLY trending or just wobbling within measurement
 * noise -- a single point-to-point delta can't tell the difference. Reflects
 * the backend's OLS fit against a real, measured noise floor (see
 * utils/trend.py), not a guess -- "confirmed" only appears once the slope
 * clears that floor, and gets vetoed back to unconfirmed if any photo in
 * range didn't align well with the baseline (trend.caveat). */
export default function TrendBadge({ trend, className = "", testId }) {
  if (!trend) return null;
  const cfg = CONFIG[trend.direction] || CONFIG.flat_or_unconfirmed;
  const Icon = cfg.icon;
  const weekly = trend.slope != null ? Math.round(trend.slope * 7 * 10) / 10 : null;
  const title = trend.slope != null
    ? `Slope: ${trend.slope} pts/day across ${trend.n} scans`
    : `${trend.n} scan${trend.n === 1 ? "" : "s"} so far -- need at least 3 to fit a trend`;

  return (
    <div className={`inline-flex flex-col gap-1 ${className}`} data-testid={testId}>
      <span
        className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full w-fit ${cfg.cls}`}
        title={title}
      >
        <Icon className="w-3.5 h-3.5" /> {cfg.label}
        {trend.confirmed && weekly != null && (
          <span className="font-normal opacity-80">({weekly > 0 ? "+" : ""}{weekly}/wk)</span>
        )}
      </span>
      {trend.caveat && (
        <span className="flex items-start gap-1 text-[11px] text-amber-600 dark:text-amber-500 max-w-xs">
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /> {trend.caveat}
        </span>
      )}
    </div>
  );
}
