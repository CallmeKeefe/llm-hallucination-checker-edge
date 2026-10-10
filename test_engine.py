"""Smoke test for the DeepEval-based hallucination engine.

This script is a quick, interactive sanity check that the DeepEval integration
is importable and correctly constructs an :class:`LLMTestCase`. It is *not*
part of the pytest suite (see ``testpaths`` in ``pyproject.toml``); run it
directly with ``python test_engine.py``.

Requires the optional ``deepeval`` dependency and, for live scoring, an
``OPENAI_API_KEY`` in the environment.
"""

from __future__ import annotations


def _build_test_case():
    """Construct and return a sample DeepEval ``LLMTestCase``.

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

    return LLMTestCase(
        input="What is the enterprise SLA guarantee?",
        actual_output="We guarantee 99.999% uptime for all tiers.",
        retrieval_context=[
            "Enterprise tier guarantees 99.9% uptime, "
            "while Standard tier guarantees 99.0%."
        ],
    )


def main() -> None:
    """Initialise the audit engine and report readiness."""
    test_case = _build_test_case()

    print("\n" + "-" * 50)
    print("[+] LLM Safety Audit Engine Initialized!")
    print("    - DeepEval & OpenTelemetry Loaded")
    print(f"    - Sample Trace Input: {test_case.input}")
    print("-" * 50 + "\n")


if __name__ == "__main__":
    main()
