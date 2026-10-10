# LLM Hallucination Checker Edge

[![CI](https://github.com/KeefeBuild/llm-hallucination-checker-edge/actions/workflows/ci.yml/badge.svg)](https://github.com/KeefeBuild/llm-hallucination-checker-edge/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, OpenTelemetry-native utility that parses GenAI trace spans and
flags silent prompt drift and ungrounded hallucinations **before** they reach
production. It runs fully offline using deterministic heuristics — no external
LLM judge required — so it drops straight into CI pipelines and edge runtimes.

## Features

- **OTel GenAI parsing** — understands the `gen_ai.*` semantic-convention
  attributes, including the transitional `gen_ai.system` namespace.
- **Heuristic risk scoring** — combines empty-completion, missing-citation, and
  instrumentation-gap signals into a single clamped `0.0–1.0` risk score.
- **Defensive by design** — malformed or partial spans never raise; they
  degrade to safe, validated defaults.
- **Typed & validated** — built on [Pydantic v2](https://docs.pydantic.dev/)
  for immutable, constrained result models.
- **Zero-LLM cost** — pure heuristics mean deterministic results and no API
  spend, ideal as a first-line gate ahead of heavier evaluation suites.

## Installation

```bash
pip install .
```

For local development (tests + coverage):

```bash
pip install ".[dev]"
```

## Quickstart

```python
from core.parser import OTELTraceParser

span = {
    "attributes": {
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.usage.input_tokens": 120,
        "gen_ai.usage.output_tokens": 45,
        "gen_ai.prompt": "According to our policy, what is the refund period?",
        "gen_ai.completion": "The refund period is 30 days. [Policy §4]",
    }
}

result = OTELTraceParser.parse_span(span)
print(result.hallucination_risk_score)  # 0.0 — grounded and complete
print(result.warnings)                  # ()  — nothing flagged
```

Evaluate an entire trace export (a JSON list, a `{"spans": [...]}` object, or a
single span):

```python
from core.parser import OTELTraceParser

results = OTELTraceParser.evaluate_trace_file("traces.json")
for r in results:
    print(f"{r.model}: risk={r.hallucination_risk_score:.2f} warnings={r.warnings}")
```

## How it works

Each span is scored against three deterministic heuristics. The final
`hallucination_risk_score` is the sum of triggered weights, clamped to `1.0`.

| Heuristic | Trigger | Weight |
| :--- | :--- | :--- |
| Empty completion | `gen_ai.completion` is missing or blank | `0.6` |
| Ungrounded citation | Prompt asks for a source (e.g. "according to") but the completion contains no `[`/`]` markers | `0.5` |
| Instrumentation gap | No model identifier could be resolved | `0.2` |

Triggered heuristics are also surfaced as human-readable entries on the result's
`warnings` tuple, and the empty-completion case emits a standard-library
`UserWarning` so it is visible in logs and catchable in tests.

## Development

```bash
# create a virtual environment and install dev extras
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install ".[dev]"

# run the test suite
pytest

# run with coverage
pytest --cov=core --cov-report=term-missing
```

Continuous integration runs the full suite on Python 3.10, 3.11, and 3.12 for
every push and pull request to `main`.

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.

