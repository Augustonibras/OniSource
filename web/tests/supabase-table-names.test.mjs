import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

async function filesUnder(directory, extensions) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(
    entries.map((entry) => {
      const filePath = path.join(directory, entry.name);
      if (entry.isDirectory()) return filesUnder(filePath, extensions);
      return extensions.some((extension) => entry.name.endsWith(extension))
        ? [filePath]
        : [];
    }),
  );
  return files.flat();
}

test("uses supplier_annotations for sourcing and never migrates mp_catalog", async () => {
  const sourceFiles = await filesUnder("src", [".ts", ".tsx"]);
  const migrationFiles = await filesUnder("supabase/migrations", [".sql"]);
  const source = (
    await Promise.all(sourceFiles.map((file) => readFile(file, "utf8")))
  ).join("\n");
  const migrations = (
    await Promise.all(migrationFiles.map((file) => readFile(file, "utf8")))
  ).join("\n");

  assert.doesNotMatch(source, /\.from\(["']annotations["']\)/);
  assert.match(source, /\.from\(["']supplier_annotations["']\)/);
  assert.doesNotMatch(
    migrations,
    /\b(?:ALTER|CREATE)\s+TABLE\s+(?:public\.)?mp_catalog\b/i,
  );
});

test("migration 005 restores the search cache columns idempotently", async () => {
  const migration = await readFile(
    "supabase/migrations/005_add_cache_key_column.sql",
    "utf8",
  );

  assert.match(
    migration,
    /ADD COLUMN IF NOT EXISTS product_cache_key TEXT/i,
  );
  assert.match(migration, /ADD COLUMN IF NOT EXISTS cas_number TEXT/i);
  assert.match(
    migration,
    /CREATE INDEX IF NOT EXISTS idx_search_results_product_cache/i,
  );
});

test("domain classification cache is product-aware, versioned, and protected by RLS", async () => {
  const migration = await readFile(
    "supabase/migrations/006_domain_classification_cache.sql",
    "utf8",
  );
  const route = await readFile("src/app/api/search/route.ts", "utf8");

  assert.match(migration, /CREATE TABLE public\.domain_classification_cache/i);
  assert.match(
    migration,
    /PRIMARY KEY \(product_cache_key, domain, prompt_version\)/i,
  );
  assert.match(
    migration,
    /ALTER TABLE public\.domain_classification_cache ENABLE ROW LEVEL SECURITY/i,
  );
  assert.match(route, /\.from\("domain_classification_cache"\)/);
  assert.match(route, /CLASSIFIER_V9_PROMPT_VERSION/);
  assert.match(route, /CLASSIFICATION_CACHE_TTL_MS/);
});
