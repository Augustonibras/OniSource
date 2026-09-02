import assert from "node:assert/strict";
import test from "node:test";

import {
  CLASSIFICATION_CACHE_TTL_MS,
  CLASSIFICATION_CONCURRENCY,
  CLASSIFICATION_TIMEOUT_MS,
  isFreshClassification,
  mapWithConcurrency,
  MAX_CLASSIFIED_DOMAINS,
  SEARCH_TIME_BUDGET_MS,
} from "../src/lib/search-execution.ts";

test("limits classification concurrency without serializing the batch", async () => {
  let active = 0;
  let maximumActive = 0;
  const results = await mapWithConcurrency(
    Array.from({ length: 12 }, (_, index) => index),
    CLASSIFICATION_CONCURRENCY,
    async (item) => {
      active += 1;
      maximumActive = Math.max(maximumActive, active);
      await new Promise((resolve) => setTimeout(resolve, 10));
      active -= 1;
      return item * 2;
    },
  );

  assert.equal(maximumActive, CLASSIFICATION_CONCURRENCY);
  assert.deepEqual(results, Array.from({ length: 12 }, (_, index) => index * 2));
});

test("keeps the production work and time ceilings fixed", () => {
  assert.equal(SEARCH_TIME_BUDGET_MS, 45_000);
  assert.equal(CLASSIFICATION_TIMEOUT_MS, 8_000);
  assert.equal(MAX_CLASSIFIED_DOMAINS, 20);
});

test("reuses domain classifications for thirty days only", () => {
  const now = Date.parse("2026-09-01T12:00:00Z");
  assert.equal(
    isFreshClassification(
      new Date(now - CLASSIFICATION_CACHE_TTL_MS).toISOString(),
      now,
    ),
    true,
  );
  assert.equal(
    isFreshClassification(
      new Date(now - CLASSIFICATION_CACHE_TTL_MS - 1).toISOString(),
      now,
    ),
    false,
  );
});
