"""Command-line interface for scoring OpenTelemetry GenAI trace exports.

This wraps :class:`core.parser.OTELTraceParser` so a trace file can be scored
straight from a terminal or wired into a CI step without any glue code. It runs
the **same** deterministic, offline heuristics used by the library, the edge
Worker, and the browser widget, so scores are consistent everywhere.

Run it either as a module::

    python -m core traces.json

or, after ``pip install .``, as an installed command::

    llm-hallucination-checker traces.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from core.parser import OTELTraceParser, TraceEvaluationResult

PROG = "llm-hallucination-checker"


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser.

    Returns:
        A configured :class:`argparse.ArgumentParser` for the CLI.
    """
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Score OpenTelemetry GenAI trace spans for hallucination risk "
            "using offline, deterministic heuristics."
        ),
    )
    parser.add_argument(
        "trace",
        help=(
            "Path to a JSON trace export: a list of spans, a {\"spans\": [...]} "
            "object, or a single span."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON instead of a human-readable table.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        metavar="T",
        help=(
            "Exit with code 1 if any span's risk score is >= T (0.0-1.0). "
            "Omit to print scores without gating."
        ),
    )
    return parser


def print_table(results: Sequence[TraceEvaluationResult]) -> None:
    """Print a human-readable per-span risk table plus a summary line.

    Args:
        results: The evaluated spans, in order.
    """
    if not results:
        print("No spans found in trace file.")
        return

    header = f"{'#':>2}  {'RISK':>5}  {'MODEL':<20}  WARNINGS"
    rule = "-" * len(header)
    print(header)
    print(rule)
    for idx, result in enumerate(results, 1):
        warnings = ", ".join(result.warnings) if result.warnings else "none"
        print(
            f"{idx:>2}  {result.hallucination_risk_score:>5.2f}  "
            f"{result.model:<20.20}  {warnings}"
        )

    worst = max(r.hallucination_risk_score for r in results)
    mean = sum(r.hallucination_risk_score for r in results) / len(results)
    print(rule)
    print(f"spans={len(results)}  mean={mean:.2f}  worst={worst:.2f}")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``llm-hallucination-checker`` command.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        A process exit code: ``0`` on success, ``1`` if a span met or exceeded
        ``--threshold``, and ``2`` on bad input (missing file or invalid JSON).
    """
    args = build_arg_parser().parse_args(argv)

    path = Path(args.trace)
    if not path.is_file():
        print(f"[!] Trace file not found: {path}", file=sys.stderr)
        return 2

    try:
        results = OTELTraceParser.evaluate_trace_file(path)
    except json.JSONDecodeError as exc:
        print(f"[!] {path} does not contain valid JSON: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        payload = [result.model_dump() for result in results]
        print(json.dumps(payload, indent=2))
    else:
        print_table(results)

    if args.threshold is not None:
        flagged = [r for r in results if r.hallucination_risk_score >= args.threshold]
        if flagged:
            print(
                f"[!] {len(flagged)} of {len(results)} span(s) met or exceeded "
                f"the {args.threshold:.2f} risk threshold.",
                file=sys.stderr,
            )
            return 1

    return 0
