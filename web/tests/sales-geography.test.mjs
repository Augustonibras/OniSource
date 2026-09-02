import assert from "node:assert/strict";
import test from "node:test";

import {
  filterSalesResultsByLocation,
  isSouthAmericaLocation,
} from "../src/lib/sales-geography.ts";

test("recognizes configured and readable South America labels", () => {
  assert.equal(isSouthAmericaLocation("continent", "south_america"), true);
  assert.equal(isSouthAmericaLocation("continent", "South America"), true);
  assert.equal(isSouthAmericaLocation("continent", "América do Sul"), true);
  assert.equal(isSouthAmericaLocation("country", "South America"), false);
});

test("removes Brazilian prospects from South America results", () => {
  const results = [
    { company: "A", country: "Brazil" },
    { company: "B", country: "Brasil" },
    { company: "C", country: "Argentina" },
    { company: "D", country: "Chile" },
  ];

  assert.deepEqual(
    filterSalesResultsByLocation(results, "continent", "south_america"),
    [results[2], results[3]],
  );
});

test("does not filter Brazil outside a South America continent search", () => {
  const results = [{ company: "A", country: "Brazil" }];
  assert.deepEqual(
    filterSalesResultsByLocation(results, "country", "Brazil"),
    results,
  );
  assert.deepEqual(
    filterSalesResultsByLocation(results, "continent", "europe"),
    results,
  );
});
