"""Standalone calibration eval for services.ai_service.analyze_metrics --
NOT a pytest test (it costs real LLM-call money and needs a labeled photo
set this repo doesn't ship). Run manually whenever the scoring prompt,
calibration text, model, or retry logic changes, to check whether scores
still track known severity instead of quietly regressing.

Usage:
    python eval_scoring_calibration.py --data-dir /path/to/labeled/photos [--limit 20]

Expects `--data-dir` to contain the photos plus a `labels.csv` with two
columns: `filename,severity` (severity = any ordered numeric scale, e.g.
Norwood-Hamilton 1-7 -- higher must mean "more hair loss" for the
correlation sign to read correctly). This tool doesn't ship or download any
dataset itself; where the 42-photo set used to build the retry/JSON-mode
fixes in this file came from (a licensed dataset's free evaluation sample --
NOT cleared for committing to a repo) is documented in commit history, not
here.
"""
import argparse
import asyncio
import base64
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from services import ai_service  # noqa: E402
from utils.constants import LLM_FAILURE_SENTINEL  # noqa: E402


def load_labels(data_dir: Path) -> list[tuple[str, int]]:
    labels_path = data_dir / "labels.csv"
    if not labels_path.exists():
        raise SystemExit(f"No labels.csv found in {data_dir} (expected columns: filename,severity)")
    rows = []
    with open(labels_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((row["filename"], int(row["severity"])))
    return rows


def to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    denom = (vx * vy) ** 0.5
    return cov / denom if denom else 0.0


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--region", default="crown")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if not os.environ.get("EMERGENT_LLM_KEY"):
        raise SystemExit("EMERGENT_LLM_KEY not set (check backend/.env) -- this eval makes real LLM calls.")

    eval_rows = load_labels(args.data_dir)
    if args.limit:
        eval_rows = eval_rows[: args.limit]

    print(f"Evaluating {len(eval_rows)} photos (region={args.region})...")
    results = []
    for i, (fname, severity) in enumerate(eval_rows, 1):
        b64 = to_b64(args.data_dir / fname)
        r = await ai_service.analyze_metrics(b64, "scan", f"eval-{i}-{fname}", region=args.region)
        print(f"  [{i}/{len(eval_rows)}] severity={severity} overall={r['overall_score']} "
              f"density={r['density_score']} coverage={r['coverage_score']} confidence={r['confidence']}")
        results.append({"file": fname, "severity": severity, **r})

    valid = [r for r in results if r["overall_score"] != LLM_FAILURE_SENTINEL]
    failed_n = len(results) - len(valid)
    print(f"\n=== SUMMARY ===")
    print(f"Total: {len(results)}, valid: {len(valid)}, failed: {failed_n} ({100 * failed_n / len(results):.1f}%)")
    if len(valid) >= 3:
        xs = [r["severity"] for r in valid]
        for key in ("overall_score", "density_score", "coverage_score"):
            ys = [r[key] for r in valid]
            print(f"Pearson r (severity vs {key}): {pearson(xs, ys):.3f}")

    out_path = args.out or (args.data_dir / "eval_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
