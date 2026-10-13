"""Unit tests for :mod:`core.parser`.

The suite exercises the parser's happy path, its edge cases (empty/missing
values, malformed shapes, non-integer tokens), its heuristic scoring and
clamping behaviour, and the standard-library warnings it emits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.parser import OTELTraceParser, TraceEvaluationResult


@pytest.fixture()
def valid_span() -> dict:
    """A well-formed span with a grounded citation and a known model."""
    return {
        "name": "chat gpt-4o",
        "attributes": {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 120,
            "gen_ai.usage.output_tokens": 45,
            "gen_ai.prompt": "According to our policy, what is the refund period?",
            "gen_ai.completion": "The refund period is 30 days. [Policy §4]",
        },
    }


def test_valid_span_reports_no_risk(valid_span: dict) -> None:
    """A grounded, complete span with a known model should score zero."""
    result = OTELTraceParser.parse_span(valid_span)

    assert isinstance(result, TraceEvaluationResult)
    assert result.model == "gpt-4o"
    assert result.input_tokens == 120
    assert result.output_tokens == 45
    assert result.hallucination_risk_score == 0.0
    assert result.warnings == ()


def test_empty_completion_raises_warning_and_scores(valid_span: dict) -> None:
    """An empty completion should emit a UserWarning and raise the score."""
    valid_span["attributes"]["gen_ai.completion"] = "   "

    with pytest.warns(UserWarning, match="Empty completion"):
        result = OTELTraceParser.parse_span(valid_span)

    assert result.hallucination_risk_score >= 0.5
    assert any("Empty completion" in warning for warning in result.warnings)


def test_ungrounded_citation_is_flagged(valid_span: dict) -> None:
    """A grounding prompt without citation markers should be flagged."""
    valid_span["attributes"]["gen_ai.prompt"] = "According to document A, summarise."
    valid_span["attributes"]["gen_ai.completion"] = "Here is the summary."

    result = OTELTraceParser.parse_span(valid_span)

    assert result.hallucination_risk_score >= 0.5
    assert any("grounding references" in warning for warning in result.warnings)


def test_score_is_clamped_to_one(valid_span: dict) -> None:
    """The aggregate score must never exceed the 1.0 upper bound."""
    # Trigger every heuristic at once: empty completion, grounding prompt, and
    # no model identifier. The raw sum (1.3) must clamp down to 1.0.
    valid_span["attributes"].pop("gen_ai.request.model")
    valid_span["attributes"]["gen_ai.prompt"] = "According to document A, summarise."
    valid_span["attributes"]["gen_ai.completion"] = ""

    with pytest.warns(UserWarning):
        result = OTELTraceParser.parse_span(valid_span)

    assert result.hallucination_risk_score == 1.0


def test_missing_model_falls_back_to_unknown(valid_span: dict) -> None:
    """A span without a model key should fall back to 'unknown-model'."""
    valid_span["attributes"].pop("gen_ai.request.model")

    result = OTELTraceParser.parse_span(valid_span)

    assert result.model == "unknown-model"
    assert any("Model identifier missing" in warning for warning in result.warnings)


def test_model_resolves_from_gen_ai_system(valid_span: dict) -> None:
    """The transitional 'gen_ai.system' attribute should resolve the model."""
    valid_span["attributes"].pop("gen_ai.request.model")
    valid_span["attributes"]["gen_ai.system"] = "anthropic"

    result = OTELTraceParser.parse_span(valid_span)

    assert result.model == "anthropic"


def test_malformed_span_does_not_raise() -> None:
    """Non-dict and attribute-less spans must degrade gracefully."""
    malformed_inputs: list[object] = ["not-a-span", {}, {"attributes": "oops"}]
    for malformed in malformed_inputs:
        # Passing non-dict input on purpose to assert the parser is defensive.
        result = OTELTraceParser.parse_span(malformed)  # type: ignore[arg-type]
        assert isinstance(result, TraceEvaluationResult)
        assert result.model == "unknown-model"


def test_non_integer_tokens_are_coerced(valid_span: dict) -> None:
    """Non-numeric or negative token values should coerce to safe defaults."""
    valid_span["attributes"]["gen_ai.usage.input_tokens"] = "not-a-number"
    valid_span["attributes"]["gen_ai.usage.output_tokens"] = -5

    result = OTELTraceParser.parse_span(valid_span)

    assert result.input_tokens == 0
    assert result.output_tokens == 0


def test_evaluate_trace_file_accepts_list(tmp_path: Path) -> None:
    """A top-level JSON list of spans should evaluate one result per span."""
    trace = [
        {
            "attributes": {
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.prompt": "Hi",
                "gen_ai.completion": "Hello [1]",
            }
        },
        {
            "attributes": {
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.prompt": "Cite the source.",
                "gen_ai.completion": "No citation here.",
            }
        },
    ]
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(trace), encoding="utf-8")

    results = OTELTraceParser.evaluate_trace_file(path)

    assert len(results) == 2
    assert results[0].hallucination_risk_score == 0.0
    assert results[1].hallucination_risk_score >= 0.5


def test_evaluate_trace_file_accepts_spans_object(tmp_path: Path) -> None:
    """An object with a top-level 'spans' key should also be supported."""
    trace = {
        "spans": [
            {
                "attributes": {
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.prompt": "Hi",
                    "gen_ai.completion": "Hello [1]",
                }
            }
        ]
    }
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(trace), encoding="utf-8")

    results = OTELTraceParser.evaluate_trace_file(str(path))

    assert len(results) == 1
    assert results[0].model == "gpt-4o"


def test_evaluate_trace_file_missing_path_raises(tmp_path: Path) -> None:
    """A non-existent trace file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        OTELTraceParser.evaluate_trace_file(tmp_path / "does-not-exist.json")


def test_parenthetical_citation_is_recognized(valid_span: dict) -> None:
    """Parenthetical author-year citations such as '(Smith, 2024)' should be recognized."""
    valid_span["attributes"]["gen_ai.prompt"] = "According to recent studies, explain the trend."
    valid_span["attributes"]["gen_ai.completion"] = "The trend has accelerated significantly (Smith, 2024)."

    result = OTELTraceParser.parse_span(valid_span)

    assert result.hallucination_risk_score == 0.0
    assert result.warnings == ()


def test_numbered_footnote_citation_is_recognized(valid_span: dict) -> None:
    """Numbered footnote markers such as '[1]' should be recognized."""
    valid_span["attributes"]["gen_ai.prompt"] = "Cite the source for the finding."
    valid_span["attributes"]["gen_ai.completion"] = "Carbon emissions decreased by 5% [1]."

    result = OTELTraceParser.parse_span(valid_span)

    assert result.hallucination_risk_score == 0.0
    assert result.warnings == ()

