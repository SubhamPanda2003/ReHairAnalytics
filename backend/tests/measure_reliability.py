"""Diagnostic tool (not a pytest test): measures how much analyze_metrics'
output varies when the SAME photo is analyzed multiple times in a row.

This is the actual instrument for the "how noisy is this really?" question --
nothing else in this codebase can answer it without live model calls, so this
has to be run against a real deployment (a real EMERGENT_LLM_KEY, either in the
environment or in backend/.env) to produce a real number. Running it against
the test stub used elsewhere in this repo will correctly report zero variance
for every metric -- that's the stub always returning the same fixed response,
not evidence the real pipeline is noise-free.

Usage (from backend/):
    python tests/measure_reliability.py path/to/photo.jpg
    python tests/measure_reliability.py path/to/photo.jpg --region crown --n 15
"""
import argparse
import asyncio
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import ai_service  # noqa: E402
from utils import image_utils  # noqa: E402

METRICS = [
    "density_score", "coverage_score", "hairline_score", "overall_score",
    "confidence", "quality", "visible_scalp_pct", "hair_coverage_pct",
]


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo", help="Path to a sample scalp/hair photo")
    ap.add_argument("--region", default="full", choices=["full", "crown", "hairline", "front", "left", "right"])
    ap.add_argument("--view", default="scan")
    ap.add_argument("--n", type=int, default=10, help="Number of independent repeat calls (default 10)")
    args = ap.parse_args()

    raw = Path(args.photo).read_bytes()
    b64 = image_utils.to_base64_jpeg(raw)

    print(f"Calling analyze_metrics {args.n} times on the same photo, region={args.region!r}...")
    results = await asyncio.gather(*[
        ai_service.analyze_metrics(b64, args.view, f"reliability-check-{i}", region=args.region)
        for i in range(args.n)
    ])

    print(f"\n{'metric':<18}{'mean':>8}{'stdev':>8}{'min':>6}{'max':>6}{'range':>7}")
    print("-" * 53)
    any_variance = False
    for key in METRICS:
        vals = [r[key] for r in results if r.get(key) is not None]
        if not vals:
            print(f"{key:<18}  n/a for region={args.region}")
            continue
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
        any_variance = any_variance or stdev > 0
        print(f"{key:<18}{mean:>8.1f}{stdev:>8.2f}{min(vals):>6}{max(vals):>6}{max(vals) - min(vals):>7}")

    if not any_variance:
        print(
            "\nEvery stdev above is 0.00 -- you're running against the test stub, not a "
            "real model (EMERGENT_LLM_KEY isn't a real key in this environment). Run this "
            "against your actual deployment to get a real noise number."
        )
    else:
        print(
            "\n'range' is the actual spread you'd see if this exact same photo got "
            "re-analyzed -- treat any week-over-week delta smaller than that as noise, "
            "not real change."
        )


if __name__ == "__main__":
    asyncio.run(main())
