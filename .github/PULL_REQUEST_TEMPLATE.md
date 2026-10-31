## Summary

What changed, and why?

## Related issue

Closes #

## Scope

- [ ] Python library / CLI
- [ ] Cloudflare Worker
- [ ] Browser widget
- [ ] Documentation
- [ ] Tests
- [ ] Privacy / security

## Three-way parity

If this changes parsing or scoring behavior, explain how the Python, Worker, and browser implementations remain consistent.

## Validation

List the exact commands run and their results.

- [ ] `pytest`
- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `cd worker && npm test` (when Worker behavior is affected)
- [ ] Positive and negative test cases added where relevant

## Privacy and compatibility

- [ ] No secrets, personal data, or real customer traces are included in tests or screenshots.
- [ ] No new runtime dependency without prior discussion.
- [ ] Public API / output changes are documented.

## Checklist

- [ ] README / docs updated where needed.
- [ ] Tests cover the change and likely regressions.
- [ ] This PR is focused and ready for review.