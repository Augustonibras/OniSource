import assert from "node:assert/strict";
import test from "node:test";

import {
  calculateEvidenceScore,
  deduplicateItemsByDomain,
  extractEvidenceSignals,
} from "../src/lib/search-quality.ts";

test("deduplicates first and second round results by normalized domain", () => {
  const first = { url: "https://example.com/product", round: 1 };
  const duplicate = { url: "https://EXAMPLE.com/about", round: 2 };
  const other = { url: "https://supplier.test", round: 2 };

  assert.deepEqual(
    deduplicateItemsByDomain(
      [first, duplicate, other],
      (result) => result.url,
    ),
    [first, other],
  );
});

test("calculates the documented evidence score", () => {
  assert.equal(
    calculateEvidenceScore({
      role: "MANUFACTURER",
      signals: {
        has_production_page: true,
        has_certifications: true,
        sells_third_party_brands: false,
        has_technical_specs: true,
      },
      fromDirectory: true,
    }),
    140,
  );
  assert.equal(
    calculateEvidenceScore({
      role: "TRADER",
      signals: {
        has_production_page: false,
        has_certifications: false,
        sells_third_party_brands: true,
        has_technical_specs: false,
      },
      autoDowngraded: true,
    }),
    -10,
  );
});

test("human manufacturer or distributor feedback fixes score at 150", () => {
  assert.equal(
    calculateEvidenceScore({
      role: "DISTRIBUTOR",
      signals: extractEvidenceSignals("no evidence"),
      classificationFeedback: "DISTRIBUTOR_CONFIRMED",
    }),
    150,
  );
});

test("extracts production, certification, third-party and technical signals", () => {
  assert.deepEqual(
    extractEvidenceSignals(
      "Our factory is ISO 9001 certified. Download the TDS. We are an authorized distributor.",
    ),
    {
      has_production_page: true,
      has_certifications: true,
      sells_third_party_brands: true,
      has_technical_specs: true,
    },
  );
});
