# LLM Hallucination Checker Edge

[![CI](https://github.com/CallmeKeefe/llm-hallucination-checker-edge/actions/workflows/ci.yml/badge.svg)](https://github.com/CallmeKeefe/llm-hallucination-checker-edge/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, OpenTelemetry-native diagnostic utility that parses GenAI trace spans
and reports structural signals such as empty completions, missing citation markers,
and missing model metadata. It uses deterministic heuristics and does not require an
external LLM judge. **It does not verify factual correctness and cannot reliably
detect hallucinations.** Treat its output as a triage signal, not a truth score or
a release gate on its own.

**▶ Live demo:** [llm-hallucination-checker.pages.dev](https://llm-hallucination-checker.pages.dev) —
paste a trace and inspect heuristic diagnostics. The *"score locally"* mode is
designed to process the trace in the browser without calling the Worker. Do not
paste secrets, personal data, customer prompts, or confidential traces into the
hosted demo; review the deployed site's privacy and logging configuration first.

## Features

- **OTel GenAI parsing** — understands the `gen_ai.*` semantic-convention
  attributes, including the transitional `gen_ai.system` namespace.
- **Heuristic diagnostics** — combines empty-completion, missing-citation-marker,
  and instrumentation-gap signals into a clamped `0.0–1.0` diagnostic score. The
  number is not a calibrated probability of hallucination or factual error.
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
print(result.warnings)  # ()  — nothing flagged
```

Evaluate an entire trace export (a JSON list, a `{"spans": [...]}` object, or a
single span):

```python
from core.parser import OTELTraceParser

results = OTELTraceParser.evaluate_trace_file("traces.json")
for r in results:
    print(f"{r.model}: risk={r.hallucination_risk_score:.2f} warnings={r.warnings}")
```

## Command-line interface

Score a whole trace file straight from the terminal — handy for CI gates and
local triage. It runs the **same** offline heuristics as the library, Worker, and
widget, so a span scores identically everywhere.

```bash
# run as a module (no install needed)
python -m core traces.json

# or install the console command
pip install .
llm-hallucination-checker traces.json
```

Example output:

```
 #   RISK  MODEL                WARNINGS
--------------------------------------------
 1   0.50  gpt-4o               Prompt requested grounding references, but no citation markers were found in the completion.
--------------------------------------------
spans=1  mean=0.50  worst=0.50
```

Useful flags:

- `--json` — emit machine-readable JSON (one object per span) instead of a table.
- `--threshold T` — exit with code `1` if **any** span scores `>= T`. Wire this
  into CI to fail a build when hallucination risk climbs. Exit codes are
  `0` (clean / below threshold), `1` (threshold exceeded), and `2` (bad input).

## Try the example traces

The [`examples/`](examples) folder contains three sample trace files, one per
outcome, so you can see the checker in action without instrumenting an app:

| File | What it demonstrates | Expected risk |
| :--- | :--- | :--- |
| `clean_trace.json` | Grounded prompt, completion includes a `[...]` citation | `0.00` (passes) |
| `missing_citation_trace.json` | Prompt asks "according to our policy", completion has no citation | `0.50` |
| `empty_completion_trace.json` | Completion is blank | `0.60` |

Run them from the repo root:

```bash
python -m core examples/clean_trace.json
python -m core examples/missing_citation_trace.json
python -m core examples/empty_completion_trace.json
```

To check that a file trips your CI gate, add `--threshold`. The
`empty_completion_trace.json` case exits with code `1` at a `0.5` threshold:

```bash
python -m core examples/empty_completion_trace.json --threshold 0.5
echo $?   # 1
```

Use `--json` to see the full structured result for any of them.

## How it works

Each span is evaluated against three deterministic heuristics. The API retains the
legacy field name `hallucination_risk_score`; interpret it only as a heuristic
structural-diagnostic score. It is not a probability, confidence interval, or
measurement of factual truth. The final value is the sum of triggered weights,
clamped to `1.0`.

| Diagnostic signal | Trigger | Contribution |
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

The edge Worker has its own dependency-free test suite (Node.js 20+):

```bash
cd worker
npm test
```

Continuous integration runs the Python suite on Python 3.10, 3.11, and 3.12 and
the Worker suite on Node 20 and 22 for every push and pull request to `main`.

## Web diagnostic widget

Want to try it without installing anything? This repo ships a lightweight,
single-page widget plus a Cloudflare Worker edge API that both run the **same
deterministic heuristics** as the Python core — a trace scores identically in
CI, at the edge, and in the browser.

```
public/index.html   # Single-page widget (paste a trace, see instant scores)
worker/index.js     # Cloudflare Worker edge API (dependency-free port)
worker/wrangler.toml
```

- **Local mode (no backend):** open `public/index.html`, tick *"Score locally
  (no network)"*, paste a trace, and the identical 0.6 / 0.5 / 0.2 heuristics
  run entirely in your browser — the trace never leaves the page.
- **Edge mode:** deploy the worker and paste its URL into the widget.

### Deploy the edge API

```bash
cd worker
npm install -g wrangler   # if you don't have it yet
wrangler login
wrangler deploy          # prints your *.workers.dev URL
```

The worker accepts a `POST` of trace JSON (a list of spans, a `{"spans":[...]}`
object, or a single span) and returns an aggregate `hallucination_risk_score`
(the mean across spans, clamped to `1.0`) plus a per-span `results` breakdown.

### Deploy the widget to Cloudflare Pages

```bash
# from the repo root, publishing the public/ directory
npx wrangler pages deploy public
```

Paste your deployed worker URL into the widget's *Edge API endpoint* field (it's
remembered in `localStorage`), or just use local mode.

## Limitations and privacy (read before use)

Honest boundaries, so nobody has to discover them the hard way:

- **Syntactic, not semantic.** The heuristics catch structural regressions —
  blank completions, missing citations, broken instrumentation. They cannot
  catch a fluent, confidently stated falsehood. Think *linter*, not *test
  suite*: it flags what looks wrong, it can't verify what is true.
- **Hand-tuned weights.** The `0.6 / 0.5 / 0.2` weights are ordered by
  confidence, not learned from data. They live in one place
  ([`core/parser.py`](core/parser.py)) and are mirrored verbatim in the edge
  worker and the browser widget — re-tune freely, in one spot.
- **Citation detection covers common bracket and parenthetical styles.** "Grounding requested" = the
  prompt contains a cue such as *according to* or *cite*; "citation present" =
  the completion contains bracket markers (`[` or `]`, including numbered footnotes like `[1]`)
  or parenthetical author-year citations like `(Smith, 2024)`. It does not perform deep bibliographic parsing.
- **Privacy is deployment-dependent.** The local browser mode is designed not to
  send trace JSON to the Worker. The hosted Worker implementation may not
  intentionally persist traces, but platform logs, observability, request metadata,
  or future code changes can affect data handling. Do not treat this README as a
  no-retention guarantee. Inspect the deployed Worker, Cloudflare settings, and
  applicable privacy notice before sending any non-public data. Prefer local mode
  for sensitive traces.

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for
the development setup, the three-way parity rule, and the pull-request process.
Thanks to everyone in [CONTRIBUTORS.md](CONTRIBUTORS.md).




## Responsible use

This project is an experimental diagnostic aid. Do not use its score as the sole basis for rejecting model outputs, evaluating people, making consequential decisions, or claiming a model is safe or factual. Validate changes with labeled false-positive and false-negative cases, keep the Python/Worker/browser implementations in parity, and review trace handling before deploying it with real user data.
