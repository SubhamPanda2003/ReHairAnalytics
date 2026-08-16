"""Statistical trend detection for score-over-time tracking (see
services.sessions.build_progress's "trend" field). A single point-to-point
delta can't tell a real change from capture/read noise; this fits a line
across ALL available points and only calls a trend "confirmed" when the
fitted slope clears a noise-floor-based threshold. A documented heuristic
(ordinary least squares + a noise-floor-aware lower bound on confidence),
not a validated statistical model -- there is no clinical ground truth this
has been checked against (see eval_noise_floor.py's docstring)."""


def combined_noise_floor(capture_noise: float, measurement_spread) -> float:
    """Combine two INDEPENDENT noise sources -- camera/framing variance
    between sessions (capture_noise, measured by eval_noise_floor.py) and
    LLM-read variance on one photo (measurement_spread, from
    services.sessions.ensemble_score) -- via root-sum-square, the standard
    way to combine independent error terms. A plain sum would overstate the
    combined uncertainty; taking the max would understate it whenever both
    sources genuinely contribute."""
    m = measurement_spread if measurement_spread is not None else 0.0
    return (capture_noise ** 2 + m ** 2) ** 0.5


def fit_trend(points: list[dict], value_key: str, noise_floor: float) -> dict:
    """OLS slope of `points[i][value_key]` against real elapsed time
    (`points[i]["date"]`, in days since the first point) -- NOT session
    index. Sessions aren't evenly spaced (same-day rescans are now
    possible), so index-based regression would treat two same-day scans as
    one full time-step apart despite zero real time having passed to change
    in. `points` must already be sorted chronologically and have at least
    one point with a real value at `value_key`.

    Returns {"slope": float|None (per day), "confirmed": bool, "direction":
    "improving"|"declining"|"flat_or_unconfirmed"|"insufficient_data", "n": int}.

    `confirmed` requires the slope to clear a threshold derived from
    noise_floor -- specifically, this never claims tighter confidence than
    the KNOWN measurement noise allows, even if this particular sample's OLS
    residuals happen to look clean by chance on a small n. That floor is the
    whole point: it's what stops a lucky-looking small sample from reporting
    a "confirmed" trend that's actually within measurement noise.
    """
    from datetime import datetime, timezone

    usable = [p for p in points if p.get(value_key) is not None]
    n = len(usable)
    if n < 3:
        return {"slope": None, "confirmed": False, "direction": "insufficient_data", "n": n}

    def _parse(d):
        dt = datetime.fromisoformat(d) if isinstance(d, str) else d
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    t0 = _parse(usable[0]["date"])
    xs = [(_parse(p["date"]) - t0).total_seconds() / 86400.0 for p in usable]
    ys = [float(p[value_key]) for p in usable]

    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        # All points landed on the same timestamp (or float precision
        # collapsed them) -- no time axis to fit a slope against.
        return {"slope": None, "confirmed": False, "direction": "insufficient_data", "n": n}

    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    residuals = [y - (my + slope * (x - mx)) for x, y in zip(xs, ys)]
    resid_se = (sum(r ** 2 for r in residuals) / max(1, n - 2)) ** 0.5
    slope_se = resid_se / (sxx ** 0.5)
    # Lower bound: even a perfect-looking small sample (near-zero residuals)
    # can't be trusted tighter than what real per-reading measurement noise
    # allows. Uses the SAME denominator as slope_se (sqrt(sxx), i.e. spread
    # of the observation times) rather than sqrt(n) -- a noise floor that
    # doesn't scale with how spread-out the sessions are in time would stay
    # just as strict for weekly scans over two months as for the same count
    # of scans crammed into three days, which is backwards: wider time
    # spread gives the same per-point noise more leverage to average out.
    floor_se = noise_floor / (sxx ** 0.5)
    effective_se = max(slope_se, floor_se)

    confirmed = abs(slope) > 1.5 * effective_se
    if not confirmed:
        direction = "flat_or_unconfirmed"
    else:
        direction = "improving" if slope > 0 else "declining"
    return {"slope": round(slope, 3), "confirmed": confirmed, "direction": direction, "n": n}
