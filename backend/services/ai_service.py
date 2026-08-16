import os
import json
import re
import logging
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from utils.constants import (
    MODEL, MEASUREMENT_TEMPERATURE, REGION_FOCUS, HAIRLINE_VISIBLE_REGIONS, LLM_FAILURE_SENTINEL,
    DENSITY_COVERAGE_DISAGREEMENT_THRESHOLD,
)

load_dotenv()
logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")


def _new_chat(session_id: str, system_message: str, temperature: float = None, json_mode: bool = False) -> LlmChat:
    """`temperature` and `json_mode` go through with_params(), NOT
    with_model(**kwargs) -- with_model() only accepts (provider, model) in the
    installed SDK version, so the old `with_model(*MODEL, temperature=...)`
    call always raised TypeError and silently fell back to the model's
    default temperature on every single call. with_params() forwards
    arbitrary kwargs straight to the underlying LiteLLM completion() call,
    which is the SDK's real extension point for this.
    json_mode sets response_format={"type": "json_object"}, which LiteLLM
    translates into Gemini's native structured-JSON mode -- the API itself
    then guarantees syntactically valid JSON instead of the model merely
    being asked to produce it in free text. A 42-photo real-Gemini test
    found ~14% of analyze_metrics() calls returned a response the regex-based
    JSON extractor couldn't parse at all; this is the fix for that failure
    class specifically (a retry covers the rest -- see analyze_metrics)."""
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system_message)
    chat.with_model(*MODEL)
    params = {}
    if temperature is not None:
        params["temperature"] = temperature
    if json_mode:
        params["response_format"] = {"type": "json_object"}
    if params:
        try:
            chat.with_params(**params)
        except Exception:
            logger.warning(f"LlmChat.with_params({list(params)}) not supported in this SDK version; continuing without it.")
    return chat


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        try:
            return json.loads(m.group(0).replace("'", '"'))
        except Exception:
            return {}


def _clamp(v, lo=0, hi=100, default=0):
    try:
        v = float(v)
    except Exception:
        return default
    return int(max(lo, min(hi, v)))


async def analyze_quality(image_b64: str, view: str, session_id: str) -> dict:
    system = (
        "You are an image quality assessment tool for standardized scalp/hair tracking photographs. "
        "You never diagnose disease. You only judge photographic quality for reliable measurement. "
        "Respond ONLY with strict JSON."
    )
    prompt = (
        f"This is a '{view}' view photo submitted for personal hair-growth tracking. "
        "Judge only whether the photo is usable for consistent measurement — be lenient. "
        "A photo is acceptable (quality >= 60) if hair is visible and reasonably in focus and lit, "
        "even if it is a casual selfie rather than a clinical top-of-scalp shot. "
        "Only score below 60 when the photo is genuinely unusable: heavy blur, extreme darkness, "
        "no hair visible at all, or wrong subject. "
        "Consider lighting, blur/sharpness, angle, distance, occlusion, resolution and hair visibility. "
        "Return strict JSON: {\"quality\": <0-100 int>, \"issues\": [<short strings>], \"retry\": <bool>}. "
        "Set retry=true only if quality < 60. Keep issues concise (max 4)."
    )
    try:
        chat = _new_chat(session_id, system, temperature=MEASUREMENT_TEMPERATURE, json_mode=True)
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        resp = await chat.send_message(msg)
        data = _extract_json(resp)
        quality = _clamp(data.get("quality"), default=70)
        issues = data.get("issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]
        issues = [str(i) for i in issues][:4]
        return {"quality": quality, "issues": issues, "retry": quality < 60}
    except Exception as e:
        logger.error(f"analyze_quality failed: {e}")
        return {"quality": 72, "issues": ["Automated quality check unavailable; accepted with default score."], "retry": False}


def _failed_metrics(include_hairline: bool) -> dict:
    return {
        "hairline_score": LLM_FAILURE_SENTINEL if include_hairline else None,
        "density_score": LLM_FAILURE_SENTINEL, "coverage_score": LLM_FAILURE_SENTINEL,
        "overall_score": LLM_FAILURE_SENTINEL, "confidence": LLM_FAILURE_SENTINEL,
        "quality": LLM_FAILURE_SENTINEL, "visible_scalp_pct": LLM_FAILURE_SENTINEL, "hair_coverage_pct": LLM_FAILURE_SENTINEL,
    }


def _is_inconsistent(result: dict) -> bool:
    """A single call's density_score and coverage_score disagreeing wildly is
    a signature of an unreliable read, not a genuine finding -- see
    DENSITY_COVERAGE_DISAGREEMENT_THRESHOLD's docstring for the real example
    that motivated this (75 vs 15 on the same photo, confidence=95)."""
    d, c = result["density_score"], result["coverage_score"]
    if d == LLM_FAILURE_SENTINEL or c == LLM_FAILURE_SENTINEL:
        return False
    return abs(d - c) > DENSITY_COVERAGE_DISAGREEMENT_THRESHOLD


async def analyze_metrics(image_b64: str, view: str, session_id: str, region: str = "full") -> dict:
    include_hairline = region in HAIRLINE_VISIBLE_REGIONS
    system = (
        "You are an objective hair measurement assistant for standardized tracking photos. "
        "You NEVER diagnose disease or give medical advice. You estimate visible photographic metrics only. "
        "Respond ONLY with strict JSON."
    )
    focus = REGION_FOCUS.get(region, REGION_FOCUS["full"])
    metrics_list = (
        "hairline_score (higher = stronger/more forward, less recession), " if include_hairline else ""
    ) + "density_score (higher = denser visible hair), coverage_score (higher = more scalp covered by hair, less visible scalp), "
    schema = ("\"hairline_score\":int," if include_hairline else "") + (
        "\"density_score\":int,\"coverage_score\":int,"
        "\"overall_score\":int,\"confidence\":int,\"quality\":int,\"visible_scalp_pct\":int,\"hair_coverage_pct\":int"
    )
    # Fixed reference points so "70" means the same thing on every photo, every
    # week, regardless of hair color, lighting, or camera exposure -- without a
    # calibration anchor the model has to invent its own sense of the scale each
    # time, which is a source of both call-to-call noise and long-term drift.
    calibration = (
        "Calibration for density_score/coverage_score: 20-35=sparse, scalp clearly dominant through the hair; "
        "45-60=moderate thinning, scalp visible but hair still the majority; "
        "65-80=healthy visible density, scalp only glimpsed on close inspection; "
        "85-100=full, no visible thinning. "
    )
    if include_hairline:
        calibration += (
            "Calibration for hairline_score: 20-35=hairline receded well past a youthful line with deep temple "
            "recession; 45-60=mild-to-moderate recession or temple thinning; 65-80=minor recession, close to a "
            "youthful line; 85-100=full, low, straight hairline with no recession. "
        )
    prompt = (
        f"Analyze this hair/scalp photo (view='{view}', focus region='{region}'). {focus} "
        f"Estimate objective visible metrics on a 0-100 scale: {metrics_list}"
        "overall_score (weighted blend). Give confidence (0-100) — how reliably this exact frame shows the "
        "focus region (low if blurry, off-angle, too far, or the region is not clearly visible). Also give "
        "quality (0-100) for photographic usability. "
        + calibration
        + ("" if include_hairline else "This view does not show the frontal hairline -- do not estimate hairline_score. ")
        + f"Return strict JSON: {{{schema}}}."
    )

    async def _attempt(attempt_session_id: str, temperature: float) -> tuple[dict, bool]:
        """One call + parse. Returns (result, was_empty) -- was_empty means
        the call succeeded but the response had no usable score fields at
        all (every field in `result` is therefore LLM_FAILURE_SENTINEL)."""
        chat = _new_chat(attempt_session_id, system, temperature=temperature, json_mode=True)
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        resp = await chat.send_message(msg)
        data = _extract_json(resp)
        empty = not data.get("density_score") and not data.get("coverage_score")
        if empty:
            # The call itself succeeded (no exception), but the response didn't
            # contain parseable/expected fields, so every score below silently
            # falls back to LLM_FAILURE_SENTINEL -- log the raw response here or
            # this failure mode is completely invisible; nothing downstream ever
            # raises for it.
            logger.warning(f"analyze_metrics: no usable score fields in response: {(resp or '')[:300]!r}")
        density = _clamp(data.get("density_score"), default=LLM_FAILURE_SENTINEL)
        coverage = _clamp(data.get("coverage_score"), default=LLM_FAILURE_SENTINEL)
        hairline = _clamp(data.get("hairline_score"), default=LLM_FAILURE_SENTINEL) if include_hairline else None
        # overall_score falls back to a blend of this call's OWN other scores
        # when the model omits it -- but only the ones that are themselves
        # real; a blend that includes a failed field would just be a
        # differently-shaped fabricated number.
        real_blend = [v for v in [density, coverage] + ([hairline] if include_hairline else []) if v != LLM_FAILURE_SENTINEL]
        overall_default = int(sum(real_blend) / len(real_blend)) if real_blend else LLM_FAILURE_SENTINEL
        overall = _clamp(data.get("overall_score"), default=overall_default)
        result = {
            "hairline_score": hairline,
            "density_score": density,
            "coverage_score": coverage,
            "overall_score": overall,
            "confidence": _clamp(data.get("confidence"), default=LLM_FAILURE_SENTINEL),
            "quality": _clamp(data.get("quality"), default=LLM_FAILURE_SENTINEL),
            "visible_scalp_pct": _clamp(data.get("visible_scalp_pct"), default=(100 - coverage) if coverage != LLM_FAILURE_SENTINEL else LLM_FAILURE_SENTINEL),
            "hair_coverage_pct": _clamp(data.get("hair_coverage_pct"), default=coverage),
        }
        return result, empty

    try:
        result, empty = await _attempt(session_id, temperature=MEASUREMENT_TEMPERATURE)
        inconsistent = _is_inconsistent(result)
        if empty or inconsistent:
            reason = "empty response" if empty else f"density/coverage disagree by {abs(result['density_score'] - result['coverage_score'])}"
            logger.warning(f"analyze_metrics: retrying once for session {session_id} ({reason})")
            # Retry at the model's DEFAULT (non-zero) temperature, not
            # MEASUREMENT_TEMPERATURE=0.0 again -- an eval run found every
            # single retry-on-empty-response case still came back empty,
            # because temperature=0 is (near-)deterministic: identical image
            # + identical prompt + identical temperature reliably reproduces
            # the identical (bad) output. A genuinely different sample is the
            # only thing a retry can offer here.
            retry_result, retry_empty = await _attempt(f"{session_id}-retry", temperature=None)
            if empty:
                # Original was a total loss -- the retry can only help, even
                # if it's imperfect (e.g. still inconsistent).
                result = retry_result
            elif not retry_empty and not _is_inconsistent(retry_result):
                # Original had real (if disagreeing) numbers -- only replace
                # them with a retry that's actually resolved, not another
                # equally-unreliable read.
                result = retry_result
        return result
    except Exception as e:
        logger.error(f"analyze_metrics failed: {e}")
        return _failed_metrics(include_hairline)


async def generate_summary(
    current: dict, previous: dict, baseline: dict, session_id: str,
    current_b64: str = None, baseline_b64: str = None, heatmap_b64: str = None,
) -> str:
    """Write the "AI insight" shown on Results/Report. When photo(s) are
    available, the model actually looks at them instead of only being handed
    numbers -- a text-only prompt can only ever restate a score delta in words,
    which reads as generic ("density improved slightly, keep it up"). Given the
    photos and the change-map heatmap, it can say WHERE it sees change (or
    doesn't), and whether that visual evidence agrees with the reported score
    movement or looks like normal photo-to-photo variation instead.
    """
    system = (
        "You are giving a hair-tracking user genuine, specific insight into their own photos and "
        "measurements -- not a script that recites numbers back at them. When photos are provided, "
        "actually describe what's visible: where hair looks fuller or thinner, whether any visible "
        "change looks concentrated in one area or spread evenly, and whether what you see agrees "
        "with the reported score movement or looks like normal photo-to-photo variation instead. "
        "If a change-map image is provided, it's the two photos aligned and diffed -- warmer "
        "(red/yellow) areas mark more visible pixel change, cooler (blue) areas mark little to none; "
        "describe roughly where the change is, don't just mention that a map was given. "
        "Never diagnose disease, never use clinical staging language, never invent a measurement you "
        "weren't given. End with exactly one specific tip grounded in what you actually observed -- "
        "not a generic reminder to be consistent. Keep the whole response under 130 words."
    )

    def diff(a, b, key):
        av, bv = a.get(key), b.get(key)
        if not b or av is None or bv is None:
            return "n/a"
        d = av - bv
        return f"{'+' if d >= 0 else ''}{d}"

    hairline_current = current.get("hairline_score")
    hairline_current = "n/a" if hairline_current is None else hairline_current
    image_notes = []
    if current_b64:
        image_notes.append("Image 1 is today's photo.")
    if baseline_b64:
        image_notes.append("Image 2 is the baseline photo to compare against.")
    if heatmap_b64:
        image_notes.append("Image 3 is the change-map (aligned diff, warm = more visible change).")
    prompt = (
        "Structured metrics (0-100 scale).\n"
        f"Current: density={current.get('density_score')}, coverage={current.get('coverage_score')}, "
        f"hairline={hairline_current}, quality/confidence={current.get('confidence')}.\n"
        f"Change vs previous: density={diff(current, previous, 'density_score')}, "
        f"coverage={diff(current, previous, 'coverage_score')}, hairline={diff(current, previous, 'hairline_score')}.\n"
        f"Change vs baseline: density={diff(current, baseline, 'density_score')}, "
        f"coverage={diff(current, baseline, 'coverage_score')}, hairline={diff(current, baseline, 'hairline_score')}.\n"
        + (" ".join(image_notes) + "\n" if image_notes else "")
        + "Write the insight now: describe what you actually observe, relate it to the measurements "
        "above, and end with one specific, grounded tip."
    )
    file_contents = []
    if current_b64:
        file_contents.append(ImageContent(image_base64=current_b64))
    if baseline_b64:
        file_contents.append(ImageContent(image_base64=baseline_b64))
    if heatmap_b64:
        file_contents.append(ImageContent(image_base64=heatmap_b64))

    try:
        chat = _new_chat(session_id, system)
        msg = UserMessage(text=prompt, file_contents=file_contents or None)
        resp = await chat.send_message(msg)
        return (resp or "").strip()
    except Exception as e:
        logger.error(f"generate_summary failed: {e}")
        return (
            "Your latest measurements were recorded successfully. Compared with earlier photos, values remained "
            "within a stable range. For the most reliable long-term trends, keep capturing photos under similar "
            "lighting, distance, and angle each week."
        )


async def generate_region_insights(regions: dict, session_id: str) -> dict:
    """Short, region-specific insight per captured scalp region in ONE call --
    so a multi-region scan's takeaway isn't one blended paragraph that hides
    which specific area actually moved (e.g. front stable, crown thinning).
    `regions` maps region_key -> {"current": metrics dict, "previous":
    metrics dict|None, "baseline": metrics dict|None, "image_b64": str|None}.
    Returns {region_key: insight str}; degrades to a generic per-region line
    on failure -- must never block the rest of the scan's analysis from saving.
    """
    region_keys = list(regions.keys())
    fallback = {reg: "No specific insight available for this region." for reg in region_keys}
    if not region_keys:
        return fallback

    system = (
        "You are giving a hair-tracking user genuine, specific insight into EACH "
        "individual region of their scalp separately -- not one blended paragraph. "
        "Never diagnose disease, never use clinical staging language, never invent "
        "a measurement you weren't given. For each region, say what the numbers show "
        "and, if a photo is given for that region, what's actually visible there -- "
        "and whether the two agree or look like normal photo-to-photo variation. "
        "Keep each region's insight to one short, specific sentence (under 30 words). "
        "Respond ONLY with strict JSON."
    )

    def diff(cur, ref, key):
        if not ref:
            return "n/a"
        cv, rv = cur.get(key), ref.get(key)
        if cv is None or rv is None:
            return "n/a"
        d = cv - rv
        return f"{'+' if d >= 0 else ''}{d}"

    lines = []
    file_contents = []
    image_idx = 0
    for reg in region_keys:
        data = regions[reg] or {}
        cur = data.get("current") or {}
        prev = data.get("previous")
        base = data.get("baseline")
        hairline = cur.get("hairline_score")
        hairline_txt = "n/a" if hairline is None else hairline
        line = (
            f"Region '{reg}': density={cur.get('density_score')}, coverage={cur.get('coverage_score')}, "
            f"hairline={hairline_txt}. Change vs previous scan: density={diff(cur, prev, 'density_score')}, "
            f"coverage={diff(cur, prev, 'coverage_score')}, hairline={diff(cur, prev, 'hairline_score')}. "
            f"Change vs baseline: density={diff(cur, base, 'density_score')}, "
            f"coverage={diff(cur, base, 'coverage_score')}, hairline={diff(cur, base, 'hairline_score')}."
        )
        if data.get("image_b64"):
            image_idx += 1
            line += f" (Image {image_idx} shows this region.)"
            file_contents.append(ImageContent(image_base64=data["image_b64"]))
        lines.append(line)

    prompt = (
        "Structured per-region metrics (0-100 scale) for today's scan, one region at a time:\n"
        + "\n".join(lines)
        + f"\n\nReturn strict JSON with exactly these keys: {json.dumps(region_keys)}. "
        "Each value is one short, specific insight sentence for that region."
    )

    try:
        chat = _new_chat(f"{session_id}:region-insights", system, json_mode=True)
        msg = UserMessage(text=prompt, file_contents=file_contents or None)
        resp = await chat.send_message(msg)
        data = _extract_json(resp)
        result = {}
        for reg in region_keys:
            val = data.get(reg)
            result[reg] = str(val).strip() if val else fallback[reg]
        return result
    except Exception as e:
        logger.error(f"generate_region_insights failed: {e}")
        return fallback


async def estimate_density_llm(image_b64: str, session_id: str) -> dict:
    """A rough hairs/cm^2 guess straight from the LLM looking at the photo --
    this IS the density estimate; there's no separate CV measurement it's
    being compared against. Clearly a guess, not a measurement, everywhere
    it's shown: the model gives its own self-reported confidence and a short
    reasoning alongside the number rather than a bare figure.
    """
    system = (
        "You are giving a rough VISUAL estimate of scalp hair density from a photo -- not a clinical or "
        "diagnostic tool, and not a substitute for one. Ground your estimate in typical clinical "
        "trichoscopy reference ranges: sparse/thinning scalp is roughly 40-120 hairs per cm^2, moderate "
        "density is roughly 120-180, healthy full density is roughly 180-250+ hairs per cm^2. "
        "Respond ONLY with strict JSON."
    )
    prompt = (
        "Look at this photo of a person's hair/scalp. Give your best rough visual guess of hair density "
        "in hairs per square centimeter (hairs_per_cm2, integer). Also give your own confidence (0-100) "
        "in this specific guess based on what's actually visible here -- low confidence if the scalp "
        "isn't clearly visible, the photo is blurry, poorly lit, or the angle makes it hard to judge. "
        "Give a one-sentence reasoning grounded in what you actually see (how much scalp shows through, "
        "hair thickness/coverage, any thinning). "
        "Return strict JSON: {\"hairs_per_cm2\":int,\"confidence\":int,\"reasoning\":str}."
    )
    try:
        chat = _new_chat(f"{session_id}:density-llm-guess", system, temperature=MEASUREMENT_TEMPERATURE, json_mode=True)
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        resp = await chat.send_message(msg)
        data = _extract_json(resp)
        try:
            hairs = max(0, int(float(data.get("hairs_per_cm2"))))
        except Exception:
            hairs = None
        reasoning = str(data.get("reasoning") or "").strip()[:300] or None
        if hairs is None:
            # The call itself succeeded but nothing usable came back -- log the
            # raw response (not just "it failed") so this is actually
            # diagnosable instead of a silent, unexplained gap in the UI.
            logger.warning(f"estimate_density_llm: no usable hairs_per_cm2 in response: {(resp or '')[:300]!r}")
        return {"hairs_per_cm2": hairs, "confidence": _clamp(data.get("confidence"), default=0), "reasoning": reasoning}
    except Exception as e:
        logger.error(f"estimate_density_llm failed: {e}")
        return {"hairs_per_cm2": None, "confidence": 0, "reasoning": None}
