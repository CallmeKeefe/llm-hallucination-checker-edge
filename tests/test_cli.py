"""Unit tests for the :mod:`core.cli` command-line interface.

These exercise the CLI's exit-code contract (0 success, 1 threshold exceeded,
2 bad input) and both output modes (table and JSON) without touching the
scoring logic itself, which is covered by ``test_parser.py``.
"""

from __future__ import annotations

import json

from core.cli import main


def _write_trace(tmp_path, spans) -> str:
    """Write ``spans`` to a JSON file and return its path as a string."""
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(spans), encoding="utf-8")
    return str(path)


def _grounded_span() -> dict:
    """A well-formed, fully grounded span that should score 0.0."""
    return {
        "attributes": {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.prompt": "According to policy, what is the refund period?",
            "gen_ai.completion": "The refund period is 30 days. [Policy §4]",
        }
    }


def test_cli_prints_table_and_exits_zero(tmp_path, capsys):
    """A clean trace prints a table and exits 0."""
    trace = _write_trace(tmp_path, [_grounded_span()])

    exit_code = main([trace])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "RISK" in out
    assert "gpt-4o" in out
    assert "spans=1" in out


def test_cli_json_output_is_valid(tmp_path, capsys):
    """--json emits a parseable JSON array of results."""
    trace = _write_trace(tmp_path, [_grounded_span()])

    exit_code = main([trace, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["model"] == "gpt-4o"
    assert payload[0]["hallucination_risk_score"] == 0.0


def test_cli_threshold_flags_risky_span(tmp_path, capsys):
    """A span scoring above --threshold exits 1 with a message on stderr."""
    risky = {
        "attributes": {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.prompt": "According to document A, summarise.",
            "gen_ai.completion": "Here is the summary.",  # grounding cue, no citation
        }
    }
    trace = _write_trace(tmp_path, [risky])

    exit_code = main([trace, "--threshold", "0.4"])

    assert exit_code == 1
    assert "risk threshold" in capsys.readouterr().err


def test_cli_threshold_passes_grounded_span(tmp_path, capsys):
    """A grounded span below --threshold exits 0."""
    trace = _write_trace(tmp_path, [_grounded_span()])

    exit_code = main([trace, "--threshold", "0.4"])

    assert exit_code == 0


def test_cli_missing_file_exits_two(capsys):
    """A missing trace file exits 2 with a helpful message."""
    exit_code = main(["does-not-exist.json"])

    assert exit_code == 2
    assert "not found" in capsys.readouterr().err


def test_cli_invalid_json_exits_two(tmp_path, capsys):
    """A file that is not valid JSON exits 2 with a helpful message."""
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")

    exit_code = main([str(path)])

    assert exit_code == 2
    assert "valid JSON" in capsys.readouterr().err
