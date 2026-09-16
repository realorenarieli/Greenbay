#!/usr/bin/env python3
"""Entrypoint: load reach-out data -> compute metrics -> write docs/dashboard.html.

Usage:
    python scripts/build_dashboard.py [DATA_PATH] [--out OUT_PATH] [--no-sample]
                                      [--slack]

  DATA_PATH   optional; defaults to data/sample_outreach.csv (CSV or JSON).
  --out       optional output path; defaults to docs/dashboard.html.
  --no-sample drops the SAMPLE banner (only use once wired to real data).
  --slack     also post the daily summary to Slack if SLACK_WEBHOOK_URL is set.

Standard library only. No pip installs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Make the package importable when run directly from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from greenbay_bdr.dashboard import write_dashboard  # noqa: E402
from greenbay_bdr.loaders import load_records  # noqa: E402
from greenbay_bdr.metrics import compute_metrics  # noqa: E402
from greenbay_bdr.notify import post_slack_summary  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Greenbay BDR dashboard.")
    parser.add_argument(
        "data_path",
        nargs="?",
        default=str(REPO_ROOT / "data" / "sample_outreach.csv"),
        help="Path to reach-out data (CSV or JSON). Defaults to the sample CSV.",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "dashboard.html"),
        help="Output HTML path. Defaults to docs/dashboard.html.",
    )
    parser.add_argument(
        "--no-sample",
        action="store_true",
        help="Drop the SAMPLE banner (only when wired to real, live data).",
    )
    parser.add_argument(
        "--slack",
        action="store_true",
        help="Also post the daily summary to Slack (needs SLACK_WEBHOOK_URL).",
    )
    args = parser.parse_args(argv)

    data_path = Path(args.data_path)
    if not data_path.exists():
        print(f"error: data file not found: {data_path}", file=sys.stderr)
        return 2

    records = load_records(data_path)
    metrics = compute_metrics(records)
    is_sample = not args.no_sample

    out = write_dashboard(
        metrics,
        args.out,
        generated_at=datetime.now(),
        source_label=data_path.name,
        sample=is_sample,
    )
    print(
        f"Wrote dashboard: {out} "
        f"({metrics.generated_for_count} records, "
        f"{metrics.first_touches_sent} first-touches, "
        f"{metrics.meetings_booked} meetings booked)"
        + ("  [SAMPLE DATA]" if is_sample else "")
    )

    if args.slack:
        posted = post_slack_summary(metrics, sample=is_sample)
        print("Slack summary posted." if posted else "Slack not configured; skipped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
