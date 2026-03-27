-- ================================================================
-- Clone Engine — Pattern Learning System
-- Każdy klon uczy system jak klonować szybciej
-- ================================================================

-- Wzorce z każdego klona
CREATE TABLE IF NOT EXISTS autonomous.clone_patterns (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    clone_id        text NOT NULL,
    product_url     text NOT NULL,
    product_name    text,
    category        text,
    features_count  int DEFAULT 0,
    tech_stack      text[] DEFAULT '{}',
    integrations    text[] DEFAULT '{}',
    feature_names   text[] DEFAULT '{}',
    analysis_json   jsonb DEFAULT '{}',
    quality_score   float DEFAULT 0,   -- ocena jakości klona (po testach)
    deploy_success  boolean DEFAULT false
);

-- Jobs generowania klonów
CREATE TABLE IF NOT EXISTS autonomous.clone_jobs (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    clone_id        text NOT NULL UNIQUE,
    source_url      text NOT NULL,
    clone_name      text,
    status          text DEFAULT 'pending',
    -- pending|analyzing|generating_sql|generating_api|
    -- generating_n8n|generating_ui|generating_worker|done|failed
    phase           int DEFAULT 0,    -- 0-7
    output_dir      text,
    error_msg       text,
    workspace       text DEFAULT 'ofshore',
    requested_by    text DEFAULT 'maciej',
    deploy_target   text,
    analysis        jsonb DEFAULT '{}',
    files_generated text[] DEFAULT '{}',
    generation_ms   int                -- czas generacji
);

-- Cache analiz (nie analizuj tego samego URL dwa razy)
CREATE TABLE IF NOT EXISTS autonomous.clone_analysis_cache (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    url_hash        text UNIQUE NOT NULL,  -- MD5 URL
    url             text NOT NULL,
    analysis        jsonb NOT NULL,
    expires_at      timestamptz DEFAULT now() + interval '7 days'
);

-- Indeksy
CREATE INDEX IF NOT EXISTS clone_patterns_category_idx
    ON autonomous.clone_patterns(category, created_at DESC);
CREATE INDEX IF NOT EXISTS clone_patterns_features_idx
    ON autonomous.clone_patterns USING gin(feature_names);
CREATE INDEX IF NOT EXISTS clone_jobs_status_idx
    ON autonomous.clone_jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS clone_cache_hash_idx
    ON autonomous.clone_analysis_cache(url_hash)
    WHERE expires_at > now();

-- RPC: Pobierz podobne wzorce dla URL
CREATE OR REPLACE FUNCTION autonomous.clone_find_similar(
    p_url       text,
    p_category  text DEFAULT NULL
)
RETURNS TABLE (
    product_name    text,
    category        text,
    feature_names   text[],
    tech_stack      text[],
    integrations    text[],
    quality_score   float,
    created_at      timestamptz
) LANGUAGE sql AS $$
    SELECT product_name, category, feature_names,
           tech_stack, integrations, quality_score, created_at
    FROM autonomous.clone_patterns
    WHERE (p_category IS NULL OR category = p_category)
      AND deploy_success = true
    ORDER BY quality_score DESC, created_at DESC
    LIMIT 5;
$$;

-- Trigger updated_at
CREATE TRIGGER clone_jobs_updated_at
    BEFORE UPDATE ON autonomous.clone_jobs
    FOR EACH ROW EXECUTE FUNCTION autonomous.set_updated_at();
