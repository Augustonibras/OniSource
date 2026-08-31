import assert from "node:assert/strict";
import test from "node:test";

import {
  appendAnnotationHistory,
  groupAnnotationHistory,
  latestAnnotation,
} from "../src/lib/annotation-history.ts";

const older = {
  id: "older",
  supplier_name: "Fornecedor A",
  status: "contacted",
  note: "Primeiro contato",
  user_email: "maria@onibras.com.br",
  created_at: "2026-08-30T12:00:00.000Z",
};
const newer = {
  id: "newer",
  supplier_name: "Fornecedor A",
  status: "waiting",
  note: "Aguardando retorno",
  user_email: "joao@onibras.com.br",
  created_at: "2026-08-31T12:00:00.000Z",
};

test("groups shared annotations and preserves chronological authorship", () => {
  const grouped = groupAnnotationHistory(
    [newer, older],
    (annotation) => annotation.supplier_name,
  );

  assert.deepEqual(grouped["fornecedor a"], [older, newer]);
  assert.equal(grouped["fornecedor a"][0].user_email, "maria@onibras.com.br");
  assert.equal(grouped["fornecedor a"][1].user_email, "joao@onibras.com.br");
  assert.equal(latestAnnotation(grouped["fornecedor a"]), newer);
});

test("appends a new annotation without overwriting history", () => {
  const history = { "fornecedor a": [older] };
  const appended = appendAnnotationHistory(history, "fornecedor a", newer);

  assert.deepEqual(appended["fornecedor a"], [older, newer]);
  assert.deepEqual(history["fornecedor a"], [older]);
});
