import assert from "node:assert/strict";
import test from "node:test";

import {
  buildProductIdentity,
  normalizeCanonicalProductName,
} from "../src/lib/product-identity.ts";

test("normalizes product names without accents, case or extra spaces", () => {
  assert.equal(
    normalizeCanonicalProductName("  Ácido   Fosfórico 85% "),
    "acido fosforico 85%",
  );
});

test("uses one CAS cache key for Portuguese, English and MP 041", () => {
  const identities = [
    buildProductIdentity("ácido fosfórico 85%", "ácido fosfórico 85%", null),
    buildProductIdentity("phosphoric acid 85%", "phosphoric acid 85%", null),
    buildProductIdentity("MP 041", "ácido fosfórico industrial", 41),
  ];

  assert.deepEqual(
    identities.map((identity) => identity.cacheKey),
    ["cas:7664-38-2", "cas:7664-38-2", "cas:7664-38-2"],
  );
});

test("uses an explicit CAS from user input as the primary cache key", () => {
  assert.equal(
    buildProductIdentity(
      "Titanium dioxide CAS 13463-67-7",
      "Titanium dioxide",
      null,
    ).cacheKey,
    "cas:13463-67-7",
  );
});
