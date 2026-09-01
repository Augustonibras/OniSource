CREATE TABLE public.domain_classification_cache (
  product_cache_key TEXT NOT NULL,
  domain TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  classification JSONB NOT NULL,
  citation_verified BOOLEAN NOT NULL DEFAULT false,
  evidence_truncated BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (product_cache_key, domain, prompt_version)
);

CREATE INDEX idx_domain_classification_cache_created
  ON public.domain_classification_cache (created_at DESC);

ALTER TABLE public.domain_classification_cache ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON TABLE public.domain_classification_cache
  TO anon, authenticated;

CREATE POLICY "Internal users can read domain classification cache"
  ON public.domain_classification_cache FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Internal users can insert domain classification cache"
  ON public.domain_classification_cache FOR INSERT
  TO anon, authenticated
  WITH CHECK (true);

CREATE POLICY "Internal users can update domain classification cache"
  ON public.domain_classification_cache FOR UPDATE
  TO anon, authenticated
  USING (true)
  WITH CHECK (true);
