import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  companyNameFromDomain,
  extractCountryFromEvidence,
  isBlockedCompanyDomain,
  NON_COMPANY_DOMAINS,
} from "../src/lib/search-result-quality.ts";

test("blocks only the configured social and community domains", () => {
  assert.deepEqual([...NON_COMPANY_DOMAINS], [
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
  ]);
  for (const domain of NON_COMPANY_DOMAINS) {
    assert.equal(isBlockedCompanyDomain(`www.${domain}`), true);
  }
  assert.equal(isBlockedCompanyDomain("news.google.com"), false);
  assert.equal(isBlockedCompanyDomain("supplier.example"), false);
});

test("derives a readable company label from the domain instead of the page title", () => {
  assert.equal(
    companyNameFromDomain("https://acido-fosforico.com/product#offer"),
    "Acido Fosforico",
  );
  assert.equal(companyNameFromDomain("www.example.com.br"), "Example");
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

test("defines six initial Tavily queries", async () => {
  const source = await readFile("src/lib/search-pipeline.ts", "utf8");
  const roundOne = source.slice(
    source.indexOf("export function buildRoundOneQueries"),
    source.indexOf("export function buildRoundTwoQueries"),
  );
  assert.equal(roundOne.match(/\n\s*query:/g)?.length, 6);
});
