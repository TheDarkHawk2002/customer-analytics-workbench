from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import InputError, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="customer-analytics",
        description="Validate synthetic support data and produce explainable customer insights.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Support-case CSV file")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Destination for reports and SQLite data")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report, summary, database = run_pipeline(args.input, args.output_dir)
    except (InputError, OSError) as exc:
        print(f"Input or output error: {exc}", file=sys.stderr)
        return 2
    print(f"Insights report: {report}")
    print(f"JSON summary: {summary}")
    print(f"SQLite snapshot: {database}")
    return 0
