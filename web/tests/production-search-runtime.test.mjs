import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("allows the production search pipeline to finish beyond one minute", async () => {
  const config = JSON.parse(await readFile("vercel.json", "utf8"));

  assert.equal(config.functions["src/app/api/**/*.ts"].maxDuration, 300);
});

