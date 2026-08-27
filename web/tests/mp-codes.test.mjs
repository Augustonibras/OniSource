import assert from "node:assert/strict";
import test from "node:test";

import { resolveMP } from "../src/data/mp-codes.ts";

test("resolves MP 46 to the configured product", () => {
  assert.deepEqual(resolveMP("MP 46"), {
    resolved: "polimero pó catiônico",
    mpCode: 46,
  });
});

test("resolves MP 110 to the configured product", () => {
  assert.deepEqual(resolveMP("MP 110"), {
    resolved: "Dióxido de titânio (Lomon R996)",
    mpCode: 110,
  });
});
