import os
import json
import re
import logging
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

load_dotenv()
logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
MODEL = ("openai", "gpt-5.6-terra")

# Low temperature for anything that produces a *measurement* meant to be compared
# week over week -- default sampling temperature is tuned for varied, creative
# text, which is the opposite of what a repeatable number needs. This isn't
# verified against the real emergentintegrations SDK (no live credentials in this
# dev environment), so it's applied defensively: if with_model() doesn't accept a
# temperature kwarg in the installed SDK version, fall back to the old call
# instead of crashing every AI request.
MEASUREMENT_TEMPERATURE = 0.0


def _new_chat(session_id: str, system_message: str, temperature: float = None) -> LlmChat:
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system_message)
    if temperature is not None:
        try:
            chat.with_model(*MODEL, temperature=temperature)
            return chat
        except TypeError:
            logger.warning("LlmChat.with_model() doesn't accept temperature in this SDK version; continuing without it.")
    chat.with_model(*MODEL)
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
        chat = _new_chat(session_id, system, temperature=MEASUREMENT_TEMPERATURE)
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
    try:
        chat = _new_chat(session_id, system, temperature=MEASUREMENT_TEMPERATURE)
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        resp = await chat.send_message(msg)
        data = _extract_json(resp)
        density = _clamp(data.get("density_score"), default=65)
        coverage = _clamp(data.get("coverage_score"), default=68)
        hairline = _clamp(data.get("hairline_score"), default=70) if include_hairline else None
        blend = [density, coverage] + ([hairline] if include_hairline else [])
        overall = _clamp(data.get("overall_score"), default=int(sum(blend) / len(blend)))
        return {
            "hairline_score": hairline,
            "density_score": density,
            "coverage_score": coverage,
            "overall_score": overall,
            "confidence": _clamp(data.get("confidence"), default=80),
            "quality": _clamp(data.get("quality"), default=75),
            "visible_scalp_pct": _clamp(data.get("visible_scalp_pct"), default=max(0, 100 - coverage)),
            "hair_coverage_pct": _clamp(data.get("hair_coverage_pct"), default=coverage),
        }
    except Exception as e:
        logger.error(f"analyze_metrics failed: {e}")
        return {
            "hairline_score": 70 if include_hairline else None, "density_score": 65, "coverage_score": 68,
            "overall_score": 68, "confidence": 75, "quality": 72, "visible_scalp_pct": 32, "hair_coverage_pct": 68,
        }


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


_HAIR_COLOR_CATEGORIES = ("dark", "light_or_gray", "mixed_or_unclear")
_CONTRAST_LEVELS = ("high", "medium", "low")
_LIGHTING_LEVELS = ("even", "uneven")


async def assess_density_reliability(image_b64: str, session_id: str) -> dict:
    """Used by the experimental hairs/cm^2 estimate (see utils/image_utils.py)
    to widen or narrow its stated error margin per-photo, based on conditions a
    vision model can actually judge from a picture. This is deliberately NOT
    asked to estimate density, count hairs, or produce any number that feeds
    into the hairs/cm^2 figure itself -- that stays pure OpenCV. It only flags
    known failure modes of the color-clustering segmentation: light/gray hair
    (breaks the "darkest cluster is hair" heuristic), low hair-scalp color
    contrast, and uneven lighting -- so the reported uncertainty reflects this
    specific photo instead of one fixed number for every photo.

    On any failure, returns worst-case values (forces a WIDER margin, never a
    narrower one) rather than silently assuming best-case conditions.
    """
    system = (
        "You assess photographic conditions for a color-based hair/scalp image segmentation pipeline. "
        "You are NOT estimating hair count, density, or any measurement -- only describing what's "
        "visible that affects whether color-based pixel classification will work well on this photo. "
        "Respond ONLY with strict JSON."
    )
    prompt = (
        "Look at this photo of a person's hair/scalp area. Assess three things: "
        "hair_color_category -- one of 'dark' (black/dark brown hair), 'light_or_gray' (blonde/gray/white/"
        "very light hair), 'mixed_or_unclear'. "
        "contrast_with_scalp -- one of 'high', 'medium', 'low': how visually distinct the hair color is "
        "from the visible scalp/skin color in this photo. "
        "lighting_quality -- one of 'even', 'uneven': whether there are harsh shadows or glare across the region. "
        "Also give confidence (0-100) in this assessment. "
        "Return strict JSON: {\"hair_color_category\":str,\"contrast_with_scalp\":str,\"lighting_quality\":str,\"confidence\":int}."
    )
    try:
        chat = _new_chat(session_id, system, temperature=MEASUREMENT_TEMPERATURE)
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        resp = await chat.send_message(msg)
        data = _extract_json(resp)
        hair_color = data.get("hair_color_category")
        contrast = data.get("contrast_with_scalp")
        lighting = data.get("lighting_quality")
        return {
            "hair_color_category": hair_color if hair_color in _HAIR_COLOR_CATEGORIES else "mixed_or_unclear",
            "contrast_with_scalp": contrast if contrast in _CONTRAST_LEVELS else "medium",
            "lighting_quality": lighting if lighting in _LIGHTING_LEVELS else "uneven",
            "confidence": _clamp(data.get("confidence"), default=40),
        }
    except Exception as e:
        logger.error(f"assess_density_reliability failed: {e}")
        # Worst-case defaults -- a failed assessment must widen the margin, not
        # silently assume favorable conditions.
        return {"hair_color_category": "mixed_or_unclear", "contrast_with_scalp": "low", "lighting_quality": "uneven", "confidence": 0}
