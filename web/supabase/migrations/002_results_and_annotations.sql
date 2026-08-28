-- Resultados de busca salvos
CREATE TABLE search_results (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  query TEXT NOT NULL,
  resolved_query TEXT,
  mp_code INTEGER,
  filters JSONB DEFAULT '{}',
  results JSONB NOT NULL,
  result_count INTEGER DEFAULT 0,
  user_email TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_search_results_query ON search_results (query);
CREATE INDEX idx_search_results_user ON search_results (user_email);
CREATE INDEX idx_search_results_created ON search_results (created_at DESC);

-- Habilitar RLS
ALTER TABLE search_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can read all results" ON search_results FOR SELECT USING (true);
CREATE POLICY "Authenticated users can insert results" ON search_results FOR INSERT WITH CHECK (true);

-- Anotações por fornecedor
CREATE TABLE supplier_annotations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  search_result_id UUID REFERENCES search_results(id) ON DELETE CASCADE,
  supplier_name TEXT NOT NULL,
  supplier_url TEXT,
  product_query TEXT NOT NULL,
  status TEXT DEFAULT 'new',
  note TEXT DEFAULT '',
  user_email TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_annotations_supplier ON supplier_annotations (supplier_name, product_query);
CREATE INDEX idx_annotations_search ON supplier_annotations (search_result_id);

ALTER TABLE supplier_annotations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can read all annotations" ON supplier_annotations FOR SELECT USING (true);
CREATE POLICY "Authenticated users can insert annotations" ON supplier_annotations FOR INSERT WITH CHECK (true);
CREATE POLICY "Authenticated users can update annotations" ON supplier_annotations FOR UPDATE USING (true);
