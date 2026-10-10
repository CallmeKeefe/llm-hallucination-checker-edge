"""LLM Hallucination Checker Edge.

A lightweight, OpenTelemetry-native utility for parsing GenAI traces and
flagging signals that correlate with hallucination and silent prompt drift.
"""

from core.parser import OTELTraceParser, TraceEvaluationResult

__all__ = ["OTELTraceParser", "TraceEvaluationResult"]
__version__ = "0.1.0"
