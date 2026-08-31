import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  CLASSIFIER_V9_PROMPT_VERSION,
  CLASSIFIER_V9_TEMPLATE,
  renderClassifierV9Prompt,
} from "../src/lib/prompts/classifier-v9.ts";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

test("TypeScript keeps a literal, hash-identical copy of the Python v9 prompt", async () => {
  const python = (await readFile("../src/search/company_classifier.py", "utf8")).replaceAll(
    "\r\n",
    "\n",
  );
  const marker = 'return f"""';
  const start = python.indexOf(marker) + marker.length;
  const end = python.indexOf('\n"""', start);
  assert.ok(start >= marker.length && end > start);
  const pythonTemplate = python.slice(start, end + 1);

  assert.equal(CLASSIFIER_V9_PROMPT_VERSION, "v9");
  assert.equal(CLASSIFIER_V9_TEMPLATE, pythonTemplate);
  assert.equal(sha256(CLASSIFIER_V9_TEMPLATE), sha256(pythonTemplate));
});

test("renders the v9 prompt without changing its literal JSON example", () => {
  const rendered = renderClassifierV9Prompt({
    domain: "HTTPS://Example.COM/",
    title: "Example",
    productContext: "phosphoric acid, CAS 7664-38-2",
    extractedContent: "Example produces phosphoric acid in its own plant.",
  });

  assert.match(rendered.prompt, /domain:\nexample\.com/);
  assert.match(rendered.prompt, /product_context:\nphosphoric acid, CAS 7664-38-2/);
  assert.match(
    rendered.prompt,
    /\{"role":"UNKNOWN","confidence":"LOW","citation":"","reasoning":"short evidence-based reason","needs_review":true\}/,
  );
  assert.equal(rendered.evidenceTruncated, false);
});
