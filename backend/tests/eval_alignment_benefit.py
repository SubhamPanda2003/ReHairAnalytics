"""Measures whether services.sessions.process_scan's per-region alignment-to-
previous-session step (image_utils.align_to_reference, added 2026-08-23)
actually reduces capture-noise sensitivity -- using the SAME synthetic-
perturbation methodology as eval_noise_floor.py, but scoring each perturbed
variant BOTH raw (no alignment -- what a scan with no previous session gets)
and aligned back to the original unperturbed photo (standing in for "the
previous session's same-region photo").

This is deliberately NOT tested with two real photos from different real
sessions: with real photos, a score difference could be either the alignment
working or the subject's hair having genuinely changed between visits, and
there's no way to tell those apart. Perturbing one real photo keeps the
"ground truth" at zero real change by construction, exactly like
eval_noise_floor.py's own premise -- any score movement is unambiguously
noise, not real change.

Alignment corrects FRAMING only (rotation/shift via homography warp) -- it
cannot correct brightness or blur. Expect it to help rotate_+3/rotate_-3/
shift_5pct specifically and do nothing for brighten_15pct/darken_15pct/
blur_mild; this script reports per-perturbation scores (not just an
aggregate spread) so that's actually visible rather than averaged away.

Not a pytest test -- costs real LLM-call money (roughly 2x eval_noise_floor.py
per photo: every perturbation gets scored twice, raw and aligned).

Usage:
    python eval_alignment_benefit.py --data-dir /path/to/photos [--limit 5]
"""
import argparse
import asyncio
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from PIL import Image, ImageEnhance, ImageFilter  # noqa: E402

from services import ai_service  # noqa: E402
from utils import image_utils  # noqa: E402
from utils.constants import LLM_FAILURE_SENTINEL  # noqa: E402

# Same perturbation set as eval_noise_floor.py, minus "original" (that's the
# alignment reference itself here, not a variant to test).
PERTURBATIONS = {
    "rotate_+3": lambda im: im.rotate(3, resample=Image.BICUBIC, fillcolor=(128, 128, 128)),
    "rotate_-3": lambda im: im.rotate(-3, resample=Image.BICUBIC, fillcolor=(128, 128, 128)),
    "brighten_15pct": lambda im: ImageEnhance.Brightness(im).enhance(1.15),
    "darken_15pct": lambda im: ImageEnhance.Brightness(im).enhance(0.85),
    "shift_5pct": lambda im: _shift(im, 0.05),
    "blur_mild": lambda im: im.filter(ImageFilter.GaussianBlur(radius=1.2)),
}


def _shift(im: Image.Image, frac: float) -> Image.Image:
    w, h = im.size
    dx, dy = int(w * frac), int(h * frac)
    shifted = Image.new("RGB", (w, h), (128, 128, 128))
    shifted.paste(im, (dx, dy))
    return shifted


def to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


async def score(image_bytes: bytes, region: str, session_id: str) -> int:
    b64 = image_utils.to_base64_jpeg_for_scoring(image_bytes)
    r = await ai_service.analyze_metrics(b64, "scan", session_id, region=region)
    return r["overall_score"]


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--region", default="crown")
    ap.add_argument("--limit", type=int, default=4, help="number of source photos to test")
    args = ap.parse_args()

    if not os.environ.get("EMERGENT_LLM_KEY"):
        raise SystemExit("EMERGENT_LLM_KEY not set (check backend/.env) -- this eval makes real LLM calls.")

    photos = sorted([p for p in args.data_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")])[: args.limit]
    if not photos:
        raise SystemExit(f"No photos found in {args.data_dir}")

    raw_spreads, aligned_spreads = [], []
    per_perturbation = {name: {"raw": [], "aligned": []} for name in PERTURBATIONS}
    all_results = []

    for photo_path in photos:
        base_img = Image.open(photo_path).convert("RGB")
        base_bytes = to_bytes(base_img)
        original_score = await score(base_bytes, args.region, f"align-orig-{photo_path.stem}")
        print(f"\n=== {photo_path.name} (original overall={original_score}) ===")

        raw_scores = [original_score]
        aligned_scores = [original_score]
        for name, fn in PERTURBATIONS.items():
            variant_bytes = to_bytes(fn(base_img))

            raw_val = await score(variant_bytes, args.region, f"align-raw-{photo_path.stem}-{name}")
            aligned_bytes, was_aligned = await asyncio.to_thread(image_utils.align_to_reference, base_bytes, variant_bytes)
            aligned_val = await score(aligned_bytes, args.region, f"align-corrected-{photo_path.stem}-{name}")

            print(f"  {name}: raw={raw_val}  aligned={aligned_val}  (homography applied: {was_aligned})")
            all_results.append({
                "photo": photo_path.name, "variant": name, "raw_overall": raw_val,
                "aligned_overall": aligned_val, "homography_applied": was_aligned,
            })
            if raw_val != LLM_FAILURE_SENTINEL:
                raw_scores.append(raw_val)
                per_perturbation[name]["raw"].append(raw_val)
            if aligned_val != LLM_FAILURE_SENTINEL:
                aligned_scores.append(aligned_val)
                per_perturbation[name]["aligned"].append(aligned_val)

        if len(raw_scores) >= 2:
            raw_spreads.append(max(raw_scores) - min(raw_scores))
        if len(aligned_scores) >= 2:
            aligned_spreads.append(max(aligned_scores) - min(aligned_scores))
        print(f"  -> spread: raw={raw_spreads[-1] if raw_spreads else 'n/a'}  aligned={aligned_spreads[-1] if aligned_spreads else 'n/a'}")

    print("\n=== SUMMARY ===")
    if raw_spreads and aligned_spreads:
        mean_raw = sum(raw_spreads) / len(raw_spreads)
        mean_aligned = sum(aligned_spreads) / len(aligned_spreads)
        print(f"Per-photo spreads (raw):     {raw_spreads} -> mean {mean_raw:.1f}")
        print(f"Per-photo spreads (aligned): {aligned_spreads} -> mean {mean_aligned:.1f}")
        print(f"Delta: {mean_aligned - mean_raw:+.1f} ({'WORSE' if mean_aligned > mean_raw else 'better'} with alignment)")
        print("\nPer-perturbation-type breakdown (mean |score - original|, lower = less sensitive):")
        for name in PERTURBATIONS:
            raws = per_perturbation[name]["raw"]
            aligneds = per_perturbation[name]["aligned"]
            if raws and aligneds:
                print(f"  {name:16s} raw_scores={raws}  aligned_scores={aligneds}")
    else:
        print("Not enough valid reads to compute spreads.")

    out_path = args.data_dir / "alignment_benefit_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
