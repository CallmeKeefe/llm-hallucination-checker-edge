"""Batch-ingest client LLM traces into DeepEval test cases.

Reads a JSON file of traces (each with ``prompt``, ``output``, and ``context``
fields) and wraps them as DeepEval :class:`LLMTestCase` objects, printing a
human-readable summary. Useful for staging client traces before running the
full hallucination evaluation suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SAMPLE_TRACES: list[dict[str, Any]] = [
    {
        "prompt": "What is our enterprise refund policy?",
        "output": "We offer a 60-day full refund with no questions asked.",
        "context": [
            "Enterprise contracts permit cancellation within 14 days of purchase."
        ],
    },
    {
        "prompt": "Can I export customer data to external CSVs?",
        "output": "Yes, you can run `SELECT *` and dump all records.",
        "context": [
            "Data export requires Admin permissions and MFA authentication."
        ],
    },
]


def process_client_traces(file_path: str | Path) -> list[Any]:
    """Load traces from ``file_path`` and return them as ``LLMTestCase`` objects.

    Args:
        file_path: Path to a JSON file containing a list of trace objects.

    Returns:
        The list of constructed ``LLMTestCase`` objects (empty if the file is
        missing or invalid).

    Raises:
        ImportError: If the optional ``deepeval`` package is not installed.
    """
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "The 'deepeval' package is required for this script. "
            "Install it with: pip install deepeval"
        ) from exc

    path = Path(file_path)
    if not path.exists():
        print(f"[!] Error: File '{path}' not found.")
        return []

    traces: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))

    print("\n" + "=" * 50)
    print(f"[+] INGESTED {len(traces)} TRACES FROM: {path}")
    print("=" * 50 + "\n")

    test_cases: list[Any] = []
    for idx, trace in enumerate(traces, 1):
        test_case = LLMTestCase(
            input=trace.get("prompt", ""),
            actual_output=trace.get("output", ""),
            retrieval_context=trace.get("context", []),
        )
        test_cases.append(test_case)

        print(f"Trace #{idx}:")
        print(f"  User Input : {test_case.input}")
        print(f"  AI Output  : {test_case.actual_output}")
        print(f"  Context    : {test_case.retrieval_context}")
        print("  Status     : Context Loaded Successfully\n")

    return test_cases


def main() -> None:
    """Write the bundled sample traces to disk and process them."""
    sample_path = Path(__file__).with_name("client_sample.json")
    sample_path.write_text(json.dumps(SAMPLE_TRACES, indent=2), encoding="utf-8")
    process_client_traces(sample_path)


if __name__ == "__main__":
    main()
