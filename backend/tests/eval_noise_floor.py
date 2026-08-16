"""Measures real CAPTURE noise -- how much analyze_metrics()'s score moves
across small photo-to-photo variations that don't represent any real change
in the subject -- as distinct from the LLM-READ noise ensemble_score already
measures (repeated reads of the IDENTICAL photo). Capture noise is what
actually happens between two real tracking sessions of the same person:
slightly different angle, distance, exposure, or focus, none of which is a
real change in their hair.

Not a pytest test -- costs real LLM-call money. Run manually to recalibrate
DEFAULT_NOISE_FLOOR whenever the capture UX, calibration prompt, or model
changes.

Usage:
    python eval_noise_floor.py --data-dir /path/to/photos [--limit 4]

`--data-dir` just needs photos in it (jpg/png) -- no labels.csv, since this
measures noise, not accuracy against a ground truth.
"""
import argparse
import asyncio
import base64
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
from utils.constants import LLM_FAILURE_SENTINEL  # noqa: E402

# Small enough that a real user genuinely wouldn't notice reproducing them
# between two sessions -- this deliberately does NOT include gross framing
# errors (those are a UX/ghost-overlay problem, not a noise-floor question).
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


def to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


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

    per_photo_spreads = []
    all_results = []
    for photo_path in photos:
        base_img = Image.open(photo_path).convert("RGB")
        variants = {"original": base_img}
        for name, fn in PERTURBATIONS.items():
            variants[name] = fn(base_img)

        print(f"\n=== {photo_path.name} ===")
        scores = {}
        for name, img in variants.items():
            b64 = to_b64(img)
            r = await ai_service.analyze_metrics(b64, "scan", f"noise-{photo_path.stem}-{name}", region=args.region)
            scores[name] = r["overall_score"]
            print(f"  {name}: overall={r['overall_score']}")
            all_results.append({"photo": photo_path.name, "variant": name, **r})

        valid_scores = [v for v in scores.values() if v != LLM_FAILURE_SENTINEL]
        if len(valid_scores) >= 2:
            spread = max(valid_scores) - min(valid_scores)
            per_photo_spreads.append(spread)
            print(f"  -> spread across {len(valid_scores)} variants (should be 0 -- nothing about the subject changed): {spread}")
        else:
            print("  -> too many failures to compute a spread for this photo")

    print("\n=== SUMMARY ===")
    if per_photo_spreads:
        mean_spread = sum(per_photo_spreads) / len(per_photo_spreads)
        print(f"Per-photo spreads: {per_photo_spreads}")
        print(f"Mean capture-noise spread across {len(per_photo_spreads)} photos: {mean_spread:.1f}")
        print("This is the real, measured capture-noise floor -- use it to set DEFAULT_NOISE_FLOOR "
              "(utils/constants.py), replacing the previous documented guess.")
    else:
        print("Not enough valid reads to compute a noise floor.")

    out_path = args.data_dir / "noise_floor_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
