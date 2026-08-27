import assert from "node:assert/strict";
import test from "node:test";

import { extractJsonArray } from "../src/lib/gemini-results.ts";

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
