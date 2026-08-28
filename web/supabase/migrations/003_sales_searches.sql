-- Buscas de vendas/prospecção
CREATE TABLE sales_searches (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  product_name TEXT NOT NULL,
  product_market TEXT NOT NULL,
  location_type TEXT NOT NULL, -- 'brazil_region', 'country', 'continent'
  location_value TEXT NOT NULL, -- 'sudeste', 'Colombia', 'south_america'
  results JSONB NOT NULL,
  result_count INTEGER DEFAULT 0,
  user_email TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sales_product ON sales_searches (product_name);
CREATE INDEX idx_sales_location ON sales_searches (location_type, location_value);
CREATE INDEX idx_sales_created ON sales_searches (created_at DESC);

ALTER TABLE sales_searches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can read all sales" ON sales_searches FOR SELECT USING (true);
CREATE POLICY "Authenticated users can insert sales" ON sales_searches FOR INSERT WITH CHECK (true);

-- Anotações de prospecção (reutiliza estrutura similar)
CREATE TABLE prospect_annotations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  sales_search_id UUID REFERENCES sales_searches(id) ON DELETE CASCADE,
  prospect_name TEXT NOT NULL,
  prospect_url TEXT,
  product_name TEXT NOT NULL,
  status TEXT DEFAULT 'new',
  note TEXT DEFAULT '',
  user_email TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prospect_annotations_search ON prospect_annotations (sales_search_id);

ALTER TABLE prospect_annotations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can read all prospect annotations" ON prospect_annotations FOR SELECT USING (true);
CREATE POLICY "Authenticated users can insert prospect annotations" ON prospect_annotations FOR INSERT WITH CHECK (true);
CREATE POLICY "Authenticated users can update prospect annotations" ON prospect_annotations FOR UPDATE USING (true);
