"""OpenTelemetry GenAI trace parsing and heuristic hallucination checks.

This module ingests spans that follow the OpenTelemetry GenAI semantic
conventions (``gen_ai.*`` attributes) and applies lightweight, fully offline
heuristics to surface signals that correlate with hallucination and silent
prompt drift. It intentionally avoids any dependency on an external LLM judge
so it can run deterministically inside CI pipelines and at the edge.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["TraceEvaluationResult", "OTELTraceParser"]


class TraceEvaluationResult(BaseModel):
    """Immutable, validated outcome of evaluating a single GenAI span."""

    model_config = ConfigDict(frozen=True)

    model: str = Field(
        default="unknown-model",
        description="LLM model identifier resolved from the span attributes.",
    )
    input_tokens: int = Field(
        default=0, ge=0, description="Prompt tokens reported by the span."
    )
    output_tokens: int = Field(
        default=0, ge=0, description="Completion tokens reported by the span."
    )
    hallucination_risk_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Aggregate heuristic risk score, clamped to the range [0.0, 1.0].",
    )
    warnings: tuple[str, ...] = Field(
        default=(),
        description="Human-readable warnings raised while evaluating the span.",
    )


class OTELTraceParser:
    """Parse GenAI spans and flag hallucination risk via deterministic heuristics.

    The parser is defensive by design: malformed spans, missing ``attributes``,
    or non-string prompt/completion values never raise; instead they degrade to
    safe defaults and, where appropriate, contribute to the risk score.
    """

    # Attribute keys following the OpenTelemetry GenAI semantic conventions.
    _MODEL_KEYS: tuple[str, ...] = ("gen_ai.request.model", "gen_ai.system")
    _INPUT_TOKENS_KEY = "gen_ai.usage.input_tokens"
    _OUTPUT_TOKENS_KEY = "gen_ai.usage.output_tokens"
    _PROMPT_KEY = "gen_ai.prompt"
    _COMPLETION_KEY = "gen_ai.completion"

    # Heuristic weights. The maximum possible sum (1.3) exceeds 1.0 on purpose
    # so the score is meaningfully clamped, exercising the safety upper bound.
    _WEIGHT_EMPTY_COMPLETION = 0.6
    _WEIGHT_MISSING_CITATION = 0.5
    _WEIGHT_UNKNOWN_MODEL = 0.2

    # A completion is considered "ungrounded" when the prompt asks for a source
    # (via one of these cues) yet the completion contains no citation markers.
    _GROUNDING_CUES: tuple[str, ...] = ("according to", "as per", "per the", "cite")
    _CITATION_MARKERS: tuple[str, ...] = ("[", "]")

    @staticmethod
    def _coerce_int(value: Any) -> int:
        """Best-effort conversion of an attribute value to a non-negative int."""
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _resolve_model(cls, attributes: dict[str, Any]) -> str:
        """Resolve the model identifier, supporting modern/transitional namespaces."""
        for key in cls._MODEL_KEYS:
            candidate = attributes.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return "unknown-model"

    @classmethod
    def parse_span(cls, span: dict[str, Any]) -> TraceEvaluationResult:
        """Evaluate a single span and return a structured, validated result.

        Args:
            span: A mapping representing an OpenTelemetry span, typically with an
                ``attributes`` dictionary following the GenAI conventions.

        Returns:
            A :class:`TraceEvaluationResult`. Never raises on malformed input.
        """
        raw_attributes = span.get("attributes", {}) if isinstance(span, dict) else {}
        attributes: dict[str, Any] = (
            raw_attributes if isinstance(raw_attributes, dict) else {}
        )

        model = cls._resolve_model(attributes)
        input_tokens = cls._coerce_int(attributes.get(cls._INPUT_TOKENS_KEY, 0))
        output_tokens = cls._coerce_int(attributes.get(cls._OUTPUT_TOKENS_KEY, 0))

        prompt = attributes.get(cls._PROMPT_KEY, "")
        completion = attributes.get(cls._COMPLETION_KEY, "")
        prompt = prompt if isinstance(prompt, str) else str(prompt)
        completion = completion if isinstance(completion, str) else str(completion)

        detected_warnings: list[str] = []
        risk_score = 0.0

        # Heuristic 1: empty or missing completion.
        if not completion.strip():
            risk_score += cls._WEIGHT_EMPTY_COMPLETION
            message = "Empty completion detected in trace span."
            detected_warnings.append(message)
            warnings.warn(message, stacklevel=2)

        # Heuristic 2: prompt requests grounding, but completion lacks citations.
        lowered_prompt = prompt.lower()
        if any(cue in lowered_prompt for cue in cls._GROUNDING_CUES) and not any(
            marker in completion for marker in cls._CITATION_MARKERS
        ):
            risk_score += cls._WEIGHT_MISSING_CITATION
            detected_warnings.append(
                "Prompt requested grounding references, but no citation markers "
                "were found in the completion."
            )

        # Heuristic 3: model identifier missing entirely (instrumentation gap).
        if model == "unknown-model":
            risk_score += cls._WEIGHT_UNKNOWN_MODEL
            detected_warnings.append("Model identifier missing from span attributes.")

        return TraceEvaluationResult(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            hallucination_risk_score=min(risk_score, 1.0),
            warnings=tuple(detected_warnings),
        )

    @classmethod
    def evaluate_trace_file(
        cls, filepath: Union[str, Path]
    ) -> list[TraceEvaluationResult]:
        """Load a trace export from disk and evaluate every span it contains.

        Accepts three common export shapes:

        * a top-level list of spans,
        * an object with a ``"spans"`` key, or
        * a single span object.

        Args:
            filepath: Path (``str`` or :class:`~pathlib.Path`) to a JSON trace file.

        Returns:
            A list with one :class:`TraceEvaluationResult` per span, in order.

        Raises:
            FileNotFoundError: If ``filepath`` does not exist.
            json.JSONDecodeError: If the file does not contain valid JSON.
        """
        path = Path(filepath)
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        return [cls.parse_span(span) for span in cls._extract_spans(data)]

    @staticmethod
    def _extract_spans(data: Any) -> list[dict[str, Any]]:
        """Normalise the parsed JSON payload into a flat list of span mappings."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("spans"), list):
            return data["spans"]
        return [data]

