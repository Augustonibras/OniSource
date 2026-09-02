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
