// -1 is the backend's LLM_FAILURE_SENTINEL: the AI call for this metric
// failed outright, rather than the metric being a real (0-100) reading.
// Treat it the same as "no reading" everywhere a score is displayed, so a
// failure renders as a clean "—" instead of a confusing negative number.
export const hasScore = (v) => v !== null && v !== undefined && v >= 0;
export const fmtScore = (v, suffix = "") => (hasScore(v) ? `${v}${suffix}` : "—");
