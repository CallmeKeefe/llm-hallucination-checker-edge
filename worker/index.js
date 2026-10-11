/**
 * Edge API handler for the LLM Hallucination Checker.
 *
 * This Cloudflare Worker is a faithful, dependency-free port of the offline
 * heuristics in `core/parser.py` (OTELTraceParser). The weights, grounding
 * cues, citation markers, model resolution, and clamping are kept identical
 * to the Python source of truth so a trace scores the same in CI as it does
 * in the browser widget. Any change to the heuristics must be mirrored here.
 *
 * Note on parity with the original sketch: the earlier draft used different
 * weights (0.5 empty / 0.3 citation) and summed spans into one score. This
 * version mirrors the tested Python core exactly (0.6 / 0.5 / 0.2) and returns
 * BOTH an aggregate (mean of per-span scores, clamped) and detailed per-span
 * results so the widget can render a full breakdown.
 */

// Heuristic weights -- keep in sync with core/parser.py.
const WEIGHT_EMPTY_COMPLETION = 0.6;
const WEIGHT_MISSING_CITATION = 0.5;
const WEIGHT_UNKNOWN_MODEL = 0.2;

// A completion is "ungrounded" when the prompt asks for a source (via one of
// these cues) yet the completion contains no citation markers.
const GROUNDING_CUES = ["according to", "as per", "per the", "cite"];
const CITATION_MARKERS = ["[", "]"];
const CITATION_PATTERNS = [/\[\d+\]/, /\([A-Z][a-z]+(?: et al\.)?,? \d{4}\)/];

// Attribute keys following the OpenTelemetry GenAI semantic conventions.
const MODEL_KEYS = ["gen_ai.request.model", "gen_ai.system"];
const INPUT_TOKENS_KEY = "gen_ai.usage.input_tokens";
const OUTPUT_TOKENS_KEY = "gen_ai.usage.output_tokens";
const PROMPT_KEY = "gen_ai.prompt";
const COMPLETION_KEY = "gen_ai.completion";

/** CORS headers shared by every response so the Pages widget can call us. */
function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

/** Build a JSON Response with CORS headers attached. */
function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

/** Best-effort conversion of an attribute value to a non-negative int. */
function coerceInt(value) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Resolve the model identifier, supporting modern/transitional namespaces. */
function resolveModel(attributes) {
  for (const key of MODEL_KEYS) {
    const candidate = attributes[key];
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return "unknown-model";
}

/** Coerce an attribute value to a string, never throwing on odd shapes. */
function asString(value) {
  return typeof value === "string" ? value : String(value ?? "");
}

/**
 * Evaluate a single span, mirroring OTELTraceParser.parse_span. Never raises
 * on malformed input -- it degrades to safe defaults instead.
 */
function parseSpan(span) {
  const rawAttributes =
    span && typeof span === "object" ? span.attributes : undefined;
  const attributes =
    rawAttributes && typeof rawAttributes === "object" ? rawAttributes : {};

  const model = resolveModel(attributes);
  const input_tokens = coerceInt(attributes[INPUT_TOKENS_KEY]);
  const output_tokens = coerceInt(attributes[OUTPUT_TOKENS_KEY]);

  const prompt = asString(attributes[PROMPT_KEY]);
  const completion = asString(attributes[COMPLETION_KEY]);

  const warnings = [];
  let risk_score = 0.0;

  // Heuristic 1: empty or missing completion.
  if (!completion.trim()) {
    risk_score += WEIGHT_EMPTY_COMPLETION;
    warnings.push("Empty completion detected in trace span.");
  }

  // Heuristic 2: prompt requests grounding, but completion lacks citations.
  const lowered_prompt = prompt.toLowerCase();
  const hasCitation =
    CITATION_MARKERS.some((marker) => completion.includes(marker)) ||
    CITATION_PATTERNS.some((pattern) => pattern.test(completion));
  if (
    GROUNDING_CUES.some((cue) => lowered_prompt.includes(cue)) &&
    !hasCitation
  ) {
    risk_score += WEIGHT_MISSING_CITATION;
    warnings.push(
      "Prompt requested grounding references, but no citation markers " +
        "were found in the completion."
    );
  }

  // Heuristic 3: model identifier missing entirely (instrumentation gap).
  if (model === "unknown-model") {
    risk_score += WEIGHT_UNKNOWN_MODEL;
    warnings.push("Model identifier missing from span attributes.");
  }

  return {
    model,
    input_tokens,
    output_tokens,
    hallucination_risk_score: Math.min(risk_score, 1.0),
    warnings,
  };
}

/** Normalise the payload into a flat list of spans (list / {spans} / single). */
function extractSpans(data) {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && Array.isArray(data.spans)) {
    return data.spans;
  }
  return [data];
}

export default {
  async fetch(request, env, ctx) {
    // Handle the CORS preflight triggered by a cross-origin JSON POST.
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (request.method !== "POST") {
      return new Response("Send a POST request with trace JSON", {
        status: 405,
        headers: corsHeaders(),
      });
    }

    try {
      const body = await request.json();
      const spans = extractSpans(body);
      const results = spans.map((span) => parseSpan(span));

      const flattenedWarnings = results.flatMap((r) => r.warnings);
      const mean =
        results.length > 0
          ? results.reduce((sum, r) => sum + r.hallucination_risk_score, 0) /
            results.length
          : 0;

      return jsonResponse({
        success: true,
        spans_evaluated: spans.length,
        hallucination_risk_score: Math.min(mean, 1.0),
        results,
        warnings: flattenedWarnings,
      });
    } catch (err) {
      return jsonResponse(
        { success: false, error: err.message || "Invalid request payload." },
        400
      );
    }
  },
};
