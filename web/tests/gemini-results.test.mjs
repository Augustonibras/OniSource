import assert from "node:assert/strict";
import test from "node:test";

import {
  extractJsonArray,
  extractJsonValue,
} from "../src/lib/gemini-results.ts";

test("extracts a classification object from a json markdown fence", () => {
  assert.equal(
    extractJsonValue(
      '```json\n{"role":"MANUFACTURER","citation":"Own {plant}","confidence":"HIGH"}\n```',
    ),
    '{"role":"MANUFACTURER","citation":"Own {plant}","confidence":"HIGH"}',
  );
});

test("extracts an array from a json markdown fence", () => {
  assert.equal(
    extractJsonArray('```json\n[{"company_name":"Example"}]\n```'),
    '[{"company_name":"Example"}]',
  );
});

test("removes text before and after the JSON array", () => {
  assert.equal(
    extractJsonArray('Here are the results:\n[{"role":"TRADER"}]\nDone.'),
    '[{"role":"TRADER"}]',
  );
});

test("returns null when no JSON array is present", () => {
  assert.equal(extractJsonArray("No suppliers found."), null);
});

test("recovers complete suppliers from a truncated JSON array", () => {
  assert.equal(
    extractJsonArray(
      '[{"company_name":"Complete"},{"company_name":"Truncated"',
    ),
    '[{"company_name":"Complete"}]',
  );
});
