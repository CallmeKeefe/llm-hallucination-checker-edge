/**
 * Automated tests for the Cloudflare Worker edge API (worker/index.js).
 *
 * These mirror the key cases in tests/test_parser.py so a divergence between
 * the Worker and the Python source of truth is caught automatically (the
 * "three-way parity" rule in CONTRIBUTING.md). Run with `npm test` from the
 * worker/ directory. Uses only Node's built-in test runner -- no dependencies.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import worker from "./index.js";

/** POST `payload` as JSON to the Worker and return the parsed response. */
async function score(payload) {
    const request = new Request("https://edge.test/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const response = await worker.fetch(request, {}, {});
    return { response, body: await response.json() };
}

/** Score a single span and return its per-span result. */
async function scoreSpan(span) {
    const { body } = await score(span);
    return body.results[0];
}

/** A well-formed span: grounded citation and a known model. */
function validSpan() {
    return {
        name: "chat gpt-4o",
        attributes: {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 120,
            "gen_ai.usage.output_tokens": 45,
            "gen_ai.prompt": "According to our policy, what is the refund period?",
            "gen_ai.completion": "The refund period is 30 days. [Policy §4]",
        },
    };
}

/** A valid span whose prompt does NOT ask for a source (no citation rule). */
function plainSpan() {
    const span = validSpan();
    span.attributes["gen_ai.prompt"] = "What is the refund period?";
    return span;
}

/** Compare floats that come from summing weights (e.g. 0.6 + 0.2). */
function assertClose(actual, expected) {
    assert.ok(
        Math.abs(actual - expected) < 1e-9,
        `expected ${expected}, got ${actual}`
    );
}

// --- Happy path -----------------------------------------------------------

test("valid span reports no risk", async () => {
    const result = await scoreSpan(validSpan());

    assert.equal(result.model, "gpt-4o");
    assert.equal(result.input_tokens, 120);
    assert.equal(result.output_tokens, 45);
    assert.equal(result.hallucination_risk_score, 0);
    assert.deepEqual(result.warnings, []);
});

test("successful response is a 200 JSON payload with the documented shape", async () => {
    const { response, body } = await score(validSpan());

    assert.equal(response.status, 200);
    assert.match(response.headers.get("Content-Type"), /application\/json/);
    assert.equal(body.success, true);
    assert.equal(body.spans_evaluated, 1);
    assert.equal(body.hallucination_risk_score, 0);
    assert.equal(body.results.length, 1);
    assert.deepEqual(body.warnings, []);
});

// --- Individual heuristics ------------------------------------------------

test("empty completion is flagged (0.6)", async () => {
    const span = plainSpan();
    span.attributes["gen_ai.completion"] = "   ";

    const result = await scoreSpan(span);

    assertClose(result.hallucination_risk_score, 0.6);
    assert.ok(result.warnings.some((w) => w.includes("Empty completion")));
});

test("missing completion attribute counts as empty", async () => {
    const span = plainSpan();
    delete span.attributes["gen_ai.completion"];

    const result = await scoreSpan(span);

    assertClose(result.hallucination_risk_score, 0.6);
});

test("ungrounded citation is flagged (0.5)", async () => {
    const span = validSpan();
    span.attributes["gen_ai.prompt"] = "According to document A, summarise.";
    span.attributes["gen_ai.completion"] = "Here is the summary.";

    const result = await scoreSpan(span);

    assertClose(result.hallucination_risk_score, 0.5);
    assert.ok(result.warnings.some((w) => w.includes("grounding references")));
});

test("every grounding cue triggers the citation heuristic", async () => {
    for (const cue of ["according to", "as per", "per the", "cite"]) {
        const span = validSpan();
        span.attributes["gen_ai.prompt"] = `Please ${cue} the handbook.`;
        span.attributes["gen_ai.completion"] = "No markers here.";

        const result = await scoreSpan(span);

        assertClose(result.hallucination_risk_score, 0.5);
    }
});

test("grounding cues are matched case-insensitively", async () => {
    const span = validSpan();
    span.attributes["gen_ai.prompt"] = "ACCORDING TO the handbook, what applies?";
    span.attributes["gen_ai.completion"] = "Nothing cited.";

    const result = await scoreSpan(span);

    assertClose(result.hallucination_risk_score, 0.5);
});

test("a citation marker satisfies a grounding prompt", async () => {
    for (const completion of ["See [1].", "Ends with a bracket]"]) {
        const span = validSpan();
        span.attributes["gen_ai.completion"] = completion;

        const result = await scoreSpan(span);

        assert.equal(result.hallucination_risk_score, 0);
    }
});

test("missing model identifier is flagged (0.2)", async () => {
    const span = validSpan();
    delete span.attributes["gen_ai.request.model"];

    const result = await scoreSpan(span);

    assert.equal(result.model, "unknown-model");
    assertClose(result.hallucination_risk_score, 0.2);
    assert.ok(result.warnings.some((w) => w.includes("Model identifier missing")));
});

test("falls back to the transitional gen_ai.system namespace", async () => {
    const span = validSpan();
    delete span.attributes["gen_ai.request.model"];
    span.attributes["gen_ai.system"] = "anthropic";

    const result = await scoreSpan(span);

    assert.equal(result.model, "anthropic");
    assert.equal(result.hallucination_risk_score, 0);
});

test("model identifier is trimmed", async () => {
    const span = validSpan();
    span.attributes["gen_ai.request.model"] = "  gpt-4o  ";

    const result = await scoreSpan(span);

    assert.equal(result.model, "gpt-4o");
});

// --- Clamping -------------------------------------------------------------

test("score is clamped to 1.0 when every heuristic fires", async () => {
    // Empty completion (0.6) + grounding prompt (0.5) + no model (0.2) = 1.3.
    const span = validSpan();
    delete span.attributes["gen_ai.request.model"];
    span.attributes["gen_ai.prompt"] = "According to document A, summarise.";
    span.attributes["gen_ai.completion"] = "";

    const result = await scoreSpan(span);

    assert.equal(result.hallucination_risk_score, 1);
});

// --- Malformed input ------------------------------------------------------

test("malformed spans degrade safely instead of throwing", async () => {
    const malformed = [
        "not-a-span",
        {},
        { attributes: "oops" },
        { attributes: null },
        { attributes: 42 },
        null,
    ];

    for (const span of malformed) {
        // Wrap in a list so `null` is scored as a span rather than the payload.
        const { response, body } = await score([span]);

        assert.equal(response.status, 200, JSON.stringify(span));
        assert.equal(body.results[0].model, "unknown-model");
        assert.ok(body.results[0].hallucination_risk_score > 0);
    }
});

test("non-integer and negative token counts coerce to zero", async () => {
    const span = validSpan();
    span.attributes["gen_ai.usage.input_tokens"] = "not-a-number";
    span.attributes["gen_ai.usage.output_tokens"] = -5;

    const result = await scoreSpan(span);

    assert.equal(result.input_tokens, 0);
    assert.equal(result.output_tokens, 0);
});

test("numeric-string token counts are accepted", async () => {
    const span = validSpan();
    span.attributes["gen_ai.usage.input_tokens"] = "250";

    const result = await scoreSpan(span);

    assert.equal(result.input_tokens, 250);
});

// --- Payload shapes and aggregation ---------------------------------------

test("accepts a top-level list, a {spans} object, and a single span", async () => {
    const span = validSpan();

    const asList = await score([span, span]);
    const asObject = await score({ spans: [span, span] });
    const asSingle = await score(span);

    assert.equal(asList.body.spans_evaluated, 2);
    assert.equal(asObject.body.spans_evaluated, 2);
    assert.equal(asSingle.body.spans_evaluated, 1);
});

test("aggregate score is the mean of the per-span scores", async () => {
    const clean = plainSpan();
    const risky = plainSpan();
    risky.attributes["gen_ai.completion"] = "";

    const { body } = await score([clean, risky]);

    assert.equal(body.results[0].hallucination_risk_score, 0);
    assertClose(body.results[1].hallucination_risk_score, 0.6);
    assertClose(body.hallucination_risk_score, 0.3);
});

test("warnings from every span are flattened into one list", async () => {
    const noModel = plainSpan();
    delete noModel.attributes["gen_ai.request.model"];
    const empty = plainSpan();
    empty.attributes["gen_ai.completion"] = "";

    const { body } = await score([noModel, empty]);

    assert.equal(body.warnings.length, 2);
});

test("an empty span list scores zero", async () => {
    const { response, body } = await score({ spans: [] });

    assert.equal(response.status, 200);
    assert.equal(body.spans_evaluated, 0);
    assert.equal(body.hallucination_risk_score, 0);
    assert.deepEqual(body.results, []);
});

// --- HTTP behaviour -------------------------------------------------------

test("OPTIONS preflight returns 204 with CORS headers", async () => {
    const response = await worker.fetch(
        new Request("https://edge.test/", { method: "OPTIONS" }),
        {},
        {}
    );

    assert.equal(response.status, 204);
    assert.equal(response.headers.get("Access-Control-Allow-Origin"), "*");
    assert.match(response.headers.get("Access-Control-Allow-Methods"), /POST/);
});

test("non-POST methods are rejected with 405", async () => {
    const response = await worker.fetch(
        new Request("https://edge.test/", { method: "GET" }),
        {},
        {}
    );

    assert.equal(response.status, 405);
    assert.equal(response.headers.get("Access-Control-Allow-Origin"), "*");
});

test("invalid JSON returns a 400 error payload", async () => {
    const response = await worker.fetch(
        new Request("https://edge.test/", { method: "POST", body: "{not json" }),
        {},
        {}
    );
    const body = await response.json();

    assert.equal(response.status, 400);
    assert.equal(body.success, false);
    assert.equal(typeof body.error, "string");
    assert.equal(response.headers.get("Access-Control-Allow-Origin"), "*");
});

// --- Parity with the shared example traces --------------------------------

test("example traces score exactly as documented in the README", async () => {
    const expected = {
        "clean_trace.json": 0,
        "missing_citation_trace.json": 0.5,
        "empty_completion_trace.json": 0.6,
    };

    for (const [file, risk] of Object.entries(expected)) {
        const url = new URL(`../examples/${file}`, import.meta.url);
        const trace = JSON.parse(readFileSync(url, "utf-8"));

        const { body } = await score(trace);

        assertClose(body.hallucination_risk_score, risk);
    }
});