import assert from "node:assert/strict";
import test from "node:test";

import {
  extractCountryFromEvidence,
  hasMinimumEvidenceScore,
  isBlockedCompanyDomain,
  isClearlyNonCompanyTitle,
  NON_COMPANY_DOMAINS,
} from "../src/lib/search-result-quality.ts";

test("blocks social media and news aggregators before classification", () => {
  for (const domain of [
    "instagram.com",
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "wikipedia.org",
    "quora.com",
  ]) {
    assert.equal(NON_COMPANY_DOMAINS.includes(domain), true);
    assert.equal(isBlockedCompanyDomain(`www.${domain}`), true);
  }
  assert.equal(isBlockedCompanyDomain("news.google.com"), true);
  assert.equal(isBlockedCompanyDomain("supplier.example"), false);
});

test("rejects page titles that clearly describe posts or listings", () => {
  assert.equal(
    isClearlyNonCompanyTitle("Top 10 Phosphoric Acid Manufacturers"),
    true,
  );
  assert.equal(
    isClearlyNonCompanyTitle("Post by Chemical Market on Instagram"),
    true,
  );
  assert.equal(
    isClearlyNonCompanyTitle(
      "What is Food Grade Phosphoric Acid Used For in Food Industry",
    ),
    true,
  );
  assert.equal(isClearlyNonCompanyTitle("Acme Phosphoric Acid"), false);
});

test("extracts country from country domains or explicit location evidence", () => {
  assert.equal(extractCountryFromEvidence("supplier.com.br", ""), "Brasil");
  assert.equal(
    extractCountryFromEvidence(
      "supplier.com",
      "Our manufacturing plant is located in China.",
    ),
    "China",
  );
  assert.equal(
    extractCountryFromEvidence(
      "supplier.com",
      "Acme is a phosphoric acid manufacturer and supplier in India.",
    ),
    "Índia",
  );
  assert.equal(
    extractCountryFromEvidence("supplier.com", "Phosphoric acid supplier."),
    "Não informado",
  );
});

test("requires an evidence score of at least 40 for display", () => {
  assert.equal(hasMinimumEvidenceScore(39), false);
  assert.equal(hasMinimumEvidenceScore(40), true);
});
