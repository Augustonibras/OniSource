ALTER TABLE public.search_results
  ADD COLUMN IF NOT EXISTS product_cache_key TEXT,
  ADD COLUMN IF NOT EXISTS cas_number TEXT;

CREATE INDEX IF NOT EXISTS idx_search_results_product_cache
  ON public.search_results (product_cache_key, created_at DESC);

ALTER TABLE public.supplier_annotations
  ADD COLUMN IF NOT EXISTS classification_feedback TEXT;

ALTER TABLE public.supplier_annotations
  ADD CONSTRAINT supplier_annotations_classification_feedback_check
  CHECK (
    classification_feedback IS NULL OR classification_feedback IN (
      'MANUFACTURER_CONFIRMED',
      'DISTRIBUTOR_CONFIRMED',
      'TRADER_CONFIRMED',
      'IRRELEVANT'
    )
  );

ALTER TABLE public.prospect_annotations
  ADD COLUMN IF NOT EXISTS classification_feedback TEXT;

ALTER TABLE public.prospect_annotations
  ADD CONSTRAINT prospect_annotations_classification_feedback_check
  CHECK (
    classification_feedback IS NULL OR classification_feedback IN (
      'MANUFACTURER_CONFIRMED',
      'DISTRIBUTOR_CONFIRMED',
      'TRADER_CONFIRMED',
      'IRRELEVANT'
    )
  );
