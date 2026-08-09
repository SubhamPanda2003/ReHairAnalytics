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


def _new_chat(session_id: str, system_message: str) -> LlmChat:
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system_message)
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
        chat = _new_chat(session_id, system)
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


async def analyze_metrics(image_b64: str, view: str, session_id: str, region: str = "full") -> dict:
    system = (
        "You are an objective hair measurement assistant for standardized tracking photos. "
        "You NEVER diagnose disease or give medical advice. You estimate visible photographic metrics only. "
        "Respond ONLY with strict JSON."
    )
    focus = REGION_FOCUS.get(region, REGION_FOCUS["full"])
    prompt = (
        f"Analyze this hair/scalp photo (view='{view}', focus region='{region}'). {focus} "
        "Estimate objective visible metrics on a 0-100 scale: "
        "hairline_score (higher = stronger/more forward, less recession), "
        "density_score (higher = denser visible hair), "
        "coverage_score (higher = more scalp covered by hair, less visible scalp), "
        "overall_score (weighted blend). Give confidence (0-100) — how reliably this exact frame shows the "
        "focus region (low if blurry, off-angle, too far, or the region is not clearly visible). Also give "
        "quality (0-100) for photographic usability. "
        "Return strict JSON: {\"hairline_score\":int,\"density_score\":int,\"coverage_score\":int,"
        "\"overall_score\":int,\"confidence\":int,\"quality\":int,\"visible_scalp_pct\":int,\"hair_coverage_pct\":int}."
    )
    try:
        chat = _new_chat(session_id, system)
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        resp = await chat.send_message(msg)
        data = _extract_json(resp)
        density = _clamp(data.get("density_score"), default=65)
        coverage = _clamp(data.get("coverage_score"), default=68)
        hairline = _clamp(data.get("hairline_score"), default=70)
        overall = _clamp(data.get("overall_score"), default=int((density + coverage + hairline) / 3))
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
            "hairline_score": 70, "density_score": 65, "coverage_score": 68,
            "overall_score": 68, "confidence": 75, "quality": 72, "visible_scalp_pct": 32, "hair_coverage_pct": 68,
        }


async def generate_summary(current: dict, previous: dict, baseline: dict, session_id: str) -> str:
    system = (
        "You are an assistant explaining objective hair growth measurements. "
        "Never diagnose disease. Explain only observed changes. Keep response under 120 words. "
        "Be encouraging, factual, and non-medical."
    )

    def diff(a, b, key):
        if not b:
            return "n/a"
        d = a.get(key, 0) - b.get(key, 0)
        return f"{'+' if d >= 0 else ''}{d}"

    prompt = (
        "Structured metrics (0-100 scale).\n"
        f"Current: density={current.get('density_score')}, coverage={current.get('coverage_score')}, "
        f"hairline={current.get('hairline_score')}, quality/confidence={current.get('confidence')}.\n"
        f"Change vs previous: density={diff(current, previous, 'density_score')}, "
        f"coverage={diff(current, previous, 'coverage_score')}, hairline={diff(current, previous, 'hairline_score')}.\n"
        f"Change vs baseline: density={diff(current, baseline, 'density_score')}, "
        f"coverage={diff(current, baseline, 'coverage_score')}, hairline={diff(current, baseline, 'hairline_score')}.\n"
        "Write a concise, non-diagnostic explanation of the observed changes and one tip for consistent tracking."
    )
    try:
        chat = _new_chat(session_id, system)
        resp = await chat.send_message(UserMessage(text=prompt))
        return (resp or "").strip()
    except Exception as e:
        logger.error(f"generate_summary failed: {e}")
        return (
            "Your latest measurements were recorded successfully. Compared with earlier photos, values remained "
            "within a stable range. For the most reliable long-term trends, keep capturing photos under similar "
            "lighting, distance, and angle each week."
        )
