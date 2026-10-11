# Contributing to LLM Hallucination Checker Edge

First off — thank you for taking the time to contribute. 🎉

This project is a small, dependency-light, OpenTelemetry-native tool that flags
hallucination and prompt-drift risk in GenAI traces using **fully offline,
deterministic heuristics** (no external LLM judge). That constraint — *no
network calls, no model scoring, deterministic output* — is the backbone of the
whole design, and every contribution should preserve it.

Following these guidelines helps communicate that you respect the maintainers'
time. In return, we'll reciprocate that respect by addressing your issues,
assessing changes, and helping you finalize pull requests.

## Table of contents

- [The golden rule: three-way parity](#the-golden-rule-three-way-parity)
- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Running the tests](#running-the-tests)
- [Coding conventions](#coding-conventions)
- [Adding or changing a heuristic](#adding-or-changing-a-heuristic)
- [Commit messages](#commit-messages)
- [Pull request process](#pull-request-process)
- [Reporting bugs](#reporting-bugs)
- [Reporting security issues](#reporting-security-issues)

## The golden rule: three-way parity

The **same** heuristics are implemented in three places, and a given trace
**must score identically** in all three:

| Surface | File | Role |
| :--- | :--- | :--- |
| Python library | [`core/parser.py`](core/parser.py) | The **source of truth**. Tested by `tests/`. |
| Edge API | [`worker/index.js`](worker/index.js) | Dependency-free Cloudflare Worker port. |
| Browser widget | [`public/index.html`](public/index.html) | The "Score locally" in-page port. |

If you change a **weight**, **grounding cue**, **citation marker**, **model key**,
or any **scoring rule**, you must mirror the change in all three files in the
same pull request. A divergence here is considered a bug — it breaks the
project's core promise that a trace scores the same in CI, at the edge, and in
the browser.

## Ways to contribute

- **Report a bug** — see [Reporting bugs](#reporting-bugs).
- **Improve documentation** — the README, docstrings, or this guide.
- **Add a heuristic or feature** — see [Adding or changing a heuristic](#adding-or-changing-a-heuristic).
- **Write tests** — especially for the edge Worker, which currently has no
  automated test harness.
- **Pick up an open issue** — issues tagged
  [`good first issue`](https://github.com/CallmeKeefe/llm-hallucination-checker-edge/labels/good%20first%20issue)
  are a great place to start.

## Development setup

You'll need **Python 3.10+**.

```bash
# 1. Fork and clone the repository, then:
git clone https://github.com/<your-username>/llm-hallucination-checker-edge.git
cd llm-hallucination-checker-edge

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows (PowerShell): venv\Scripts\Activate.ps1

# 3. Install the package with dev extras (pytest + coverage)
pip install ".[dev]"

# 4. (Optional) install the CLI as a command
pip install .
```

To work on the Cloudflare Worker or the widget you'll also want
[Node.js](https://nodejs.org/) and [Wrangler](https://developers.cloudflare.com/workers/wrangler/)
(`npm install -g wrangler`).

## Running the tests

```bash
# run the full suite
pytest

# run with a coverage report (matches CI)
pytest --cov=core --cov-report=term-missing
```

CI runs the suite on **Python 3.10, 3.11, and 3.12** for every push and pull
request to `main`. Please make sure the suite is green locally before opening a
PR.

You can also exercise the CLI end-to-end:

```bash
python -m core client_sample.json            # human-readable table
python -m core client_sample.json --json     # machine-readable output
python -m core client_sample.json --threshold 0.5   # non-zero exit if any span >= 0.5
```

## Coding conventions

- **Type hints everywhere.** All public functions and methods are annotated.
- **Docstrings** on every public module, class, function, and method. This
  project uses the Google-style `Args:` / `Returns:` / `Raises:` sections — see
  `core/parser.py` for the canonical example.
- **Defensive parsing.** The parser must **never raise** on malformed input;
  it degrades to safe, validated defaults. Preserve this property.
- **Immutability.** Result models are frozen Pydantic v2 models
  (`model_config = ConfigDict(frozen=True)`).
- **Formatting.** Keep lines reasonable (~88 cols) and match the surrounding
  style. `core/parser.py` is the reference for tone and structure.
- **No new runtime dependencies** without discussion. The only runtime
  dependency is `pydantic`; dev dependencies are `pytest` and `pytest-cov`.

## Adding or changing a heuristic

This is the most involved change type, because of the parity rule. When you add
or modify a heuristic:

1. Update [`core/parser.py`](core/parser.py) — add the weight, the cue/marker
   tuples, and the scoring branch. Update the module/class docstrings and the
   comment that documents the maximum raw weight sum.
2. Mirror the exact same logic in [`worker/index.js`](worker/index.js).
3. Mirror it again in the local scorer inside [`public/index.html`](public/index.html).
4. Add a unit test in [`tests/test_parser.py`](tests/test_parser.py) covering
   the new behaviour (and update the clamp test if the max sum changes).
5. Update the **heuristics table** in the README ("How it works") and, if
   relevant, the "Limitations" section.
6. Note the change in your pull request description.

## Commit messages

This project follows [Conventional Commits](https://www.conventionalcommits.org/).
Prefix your commit subject with one of:

- `feat:` — a new feature
- `fix:` — a bug fix
- `docs:` — documentation only
- `test:` — adding or correcting tests
- `chore:` — tooling, dependencies, config
- `refactor:` — code change that neither fixes a bug nor adds a feature

Example: `feat: flag hedging language in completions`.

Keep the subject in the imperative mood ("add", not "added") and under ~72
characters.

## Pull request process

1. Fork the repo and create your branch from `main`.
2. Make your changes, keeping the three-way parity rule in mind.
3. Ensure `pytest` passes and you've added/updated tests.
4. Update documentation (README, docstrings) as needed.
5. Open a pull request against `main` with a clear description of **what** and
   **why**, and reference any related issue (e.g. "Closes #12").
6. Be ready to make a few revisions — maintainers may request changes.

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).

## Reporting bugs

Before opening a new issue, please [search existing
issues](https://github.com/CallmeKeefe/llm-hallucination-checker-edge/issues) to
avoid duplicates. A great bug report includes:

- A clear, descriptive title.
- The exact steps to reproduce (a minimal trace JSON is ideal).
- The expected result vs. the actual result.
- Your environment: OS, Python version, and whether you used the library, the
  Worker, or the widget.
- If the surfaces disagree, say **which** surfaces and show the differing
  scores — parity bugs are high priority.

## Reporting security issues

Please do **not** open a public issue for security vulnerabilities. Instead,
email the maintainer (see the author contact in
[`pyproject.toml`](pyproject.toml)) with details, and we'll coordinate a fix and
disclosure.

---

Thanks again for helping make LLM output a little safer to ship. 💙

