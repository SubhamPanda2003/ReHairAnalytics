"""Tuning constants and lookup tables for the AI scoring, ensembling, and
image-alignment pipeline -- centralized so a change like swapping the LLM
model or adjusting a threshold is a single edit instead of a search across
files. Environment-derived settings (secrets, deploy config) stay in
utils/config.py; everything here is a hardcoded, code-owned value.
"""

# --- LLM (services/ai_service.py) ---

# Gemini 2.5 Flash: confirmed multimodal (text/image/video/audio in, text out),
# which every call needs since each one sends at least one photo.
MODEL = ("gemini", "gemini-2.5-flash")

# Low temperature for anything that produces a *measurement* meant to be compared
# week over week -- default sampling temperature is tuned for varied, creative
# text, which is the opposite of what a repeatable number needs. This isn't
# verified against the real emergentintegrations SDK (no live credentials in this
# dev environment), so it's applied defensively in ai_service._new_chat: if
# with_model() doesn't accept a temperature kwarg in the installed SDK version,
# it falls back to the old call instead of crashing every AI request.
MEASUREMENT_TEMPERATURE = 0.0

REGION_FOCUS = {
    "full": "Assess the entire visible scalp and hair evenly.",
    "crown": "Focus specifically on the CROWN / VERTEX (top-back) area — its density and how much scalp shows through there.",
    "hairline": "Focus specifically on the FRONTAL HAIRLINE and temples — the boundary position, peak, and any temple recession.",
}

# The frontal hairline isn't visible from the crown, the back of the head, or a
# straight-down top shot -- asking the model to score it there just produces a
# guess with no anatomical basis, and that guess was previously getting averaged
# into the headline hairline score. Only request/report hairline_score for views
# where it's actually in frame.
HAIRLINE_VISIBLE_REGIONS = {"full", "front", "hairline", "left", "right"}


# Marks a score field the LLM call couldn't actually produce (call raised, or
# the response had no usable value for that field) -- distinct from a real
# score AND from None ("not applicable to this region", e.g. hairline_score
# off a crown photo). Deliberately outside the valid 0-100 range so it can
# never be mistaken for a real reading, but still a plain int so it flows
# through existing max()/sort()/sum() call sites without crashing -- it just
# sorts/averages as the worst possible value, which is the correct behavior
# (real data should always be preferred over a known-failed reading).
LLM_FAILURE_SENTINEL = -1

# A single call's density_score and coverage_score disagreeing by more than
# this is treated as an unreliable read worth retrying once, not a genuine
# finding -- found via a 42-photo real-Gemini test where one read came back
# density=75/coverage=15 (same photo) with confidence=95, i.e. the model's
# own confidence didn't flag it. Set well above normal legitimate spread
# (diffuse thinning can genuinely show moderately different density vs
# coverage) so this only catches the wild, clearly-wrong cases.
DENSITY_COVERAGE_DISAGREEMENT_THRESHOLD = 40

# --- Scoring / ensembling (services/sessions.py) ---

# hairline_score is handled separately from the other metrics: it's only ever
# populated for frames from a region where a frontal hairline is actually visible
# (see HAIRLINE_VISIBLE_REGIONS above), so it can't be blindly averaged alongside
# metrics every frame has.
METRIC_KEYS = [
    "density_score", "coverage_score", "overall_score",
    "confidence", "quality_score", "visible_scalp_pct", "hair_coverage_pct",
]
DELTA_KEYS = ("density", "coverage", "hairline", "overall")
BLUR_QUALITY_MIN = 40

# How many independent times to re-analyze the single photo that ends up
# representing each region, before finalizing its score. A vision-LLM call is a
# stochastic sample, not a fixed readout -- one call is one sample of that noise.
# Applied only to the frame that actually wins each region (not every captured
# frame) to keep the added cost/latency bounded: for a 6-region scan this adds
# up to 6 * (ENSEMBLE_N - 1) extra calls, not 30+. Gated behind /scan's
# `precision` flag -- off skips ensembling entirely and scores from one read.
ENSEMBLE_N = 3

# Auto-scan frames carry a `region` (front/left/right/crown/hairline/back); manual
# uploads carry a `view` (front/top/left/right/back) instead -- present order for
# whichever tag is available.
REGION_ORDER = ["front", "left", "right", "crown", "hairline", "back", "top"]

# A single early session's score is just as noisy as any other single reading --
# if that one day happened to get an unlucky AI call, every future comparison
# inherits that error forever. Blending the first few sessions' scores together
# makes the reference point itself less sensitive to one bad day. The baseline
# *photo* deliberately stays single-session (pixels can't be averaged the same
# way, and change-maps needs one concrete image to align against).
BASELINE_BLEND_N = 3

# How much a photo-to-photo CAPTURE difference alone (slightly different
# angle/exposure/focus between two real sessions of the same person, nothing
# about their hair actually changed) moves analyze_metrics()'s overall_score
# -- measured via tests/eval_noise_floor.py's synthetic-perturbation eval,
# not assumed. Combined with a session's own measured LLM-read spread (see
# services.sessions.build_progress -> utils.trend.combined_noise_floor) to
# get the real noise floor a trend has to clear before it's "confirmed".
#
# Measured 2026-08-16 against 3 real photos (crown region, gemini-2.5-flash):
# per-photo overall_score spread across 6 small perturbations (±3° rotation,
# ±15% brightness, 5% shift, mild blur) was 13, 2, and 37 -- mean 17.3,
# rounded here. That's ~4x the previous ASSUMED value of 4; a 3-degree
# rotation alone swung one photo's score from 30 to 65. Small sample (n=3),
# so treat the exact number loosely, but the direction is unambiguous:
# capture noise is large enough that most single-session-to-session deltas
# this app would previously have called a "trend" are within noise.
# TODO: re-measure (bigger sample) and update after any capture-flow,
# calibration prompt, or model change -- it will drift out of date otherwise.
CAPTURE_NOISE_FLOOR = 4


# --- Image alignment (utils/image_utils.py) ---
MIN_ALIGN_MATCHES = 10
