ALTER TABLE public.search_results
  ADD COLUMN IF NOT EXISTS product_cache_key TEXT,
  ADD COLUMN IF NOT EXISTS cas_number TEXT;

CREATE INDEX IF NOT EXISTS idx_search_results_product_cache
  ON public.search_results (product_cache_key, created_at DESC);
