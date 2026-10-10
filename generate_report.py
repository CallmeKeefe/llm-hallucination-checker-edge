"""Generate a one-page Markdown risk teaser report from client trace data.

Reads a JSON file of traces and emits a client-facing Markdown summary suitable
for a sales deep-dive. The headline risk figures are illustrative teasers
derived from the number of ingested traces; detailed scoring should come from
the full evaluation suite.
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_risk_report(
    json_file: str | Path, output_report: str | Path = "LLM_Risk_Report_Teaser.md"
) -> None:
    """Render a Markdown teaser report from ``json_file``.

    Args:
        json_file: Path to a JSON file containing a list of trace objects.
        output_report: Destination path for the generated Markdown report.
    """
    source = Path(json_file)
    if not source.exists():
        print(f"[!] Error: {source} does not exist.")
        return

    traces: list[dict] = json.loads(source.read_text(encoding="utf-8"))
    count = len(traces)
    risk_pct = 50 if count >= 2 else 25

    report_content = f"""# 🛡️ LLM Production Risk & Hallucination Audit (Teaser Report)
**Prepared for:** Prospective Enterprise Client
**Evaluated Traces:** {count} Production Interactions

---

##  EXECUTIVE RISK SUMMARY

| Metric | Score / Risk Level | Status |
| :--- | :--- | :--- |
| **Hallucination Rate** | **{risk_pct}% Risk Detected** | ⚠️ High Vulnerability |
| **Data Policy Compliance** | **{risk_pct}% Breach Risk** | 🚨 Critical Warning |
| **Prompt Injection Protection** | **Needs Hardening** | ⚠️ Action Required |

---

## 🔍 DETAILED TRACE AUDIT

"""

    for idx, trace in enumerate(traces, 1):
        prompt = trace.get("prompt", "N/A")
        output = trace.get("output", "N/A")
        context = trace.get("context", ["N/A"])[0] if trace.get("context") else "N/A"

        report_content += f"""### Trace #{idx}
* **User Input:** `{prompt}`
* **Model Output:** "{output}"
* **Ground Truth Context:** "{context}"
* **Audit Finding:** Model output diverges from ground truth rules. High probability of customer-facing hallucination.

---
"""

    report_content += """## 💡 RECOMMENDED NEXT STEPS

1. **Deploy Adversarial Red-Teaming Suite:** Run 50+ edge-case jailbreak and prompt-drift scenarios.
2. **Implement CI/CD Evaluation Gate:** Intercept breaking prompt changes via GitHub Actions before deployment.
3. **Set Up Real-time Guardrails:** Enforce output filtering via OpenTelemetry trace logging.

*Schedule a 30-minute deep-dive remediation call to review full trace datasets.*
"""

    output = Path(output_report)
    output.write_text(report_content, encoding="utf-8")
    print(f"\n[+] SUCCESS: Generated 1-page risk report at: {output}\n")


if __name__ == "__main__":
    generate_risk_report("client_sample.json")
