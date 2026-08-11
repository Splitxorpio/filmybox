-- Adds 'social_estimate' as a distinct budget_confidence tier - crowd-sourced
-- (Bluesky post consensus), not a curated/structured source, so it must
-- stay distinguishable from 'confirmed'/'estimated' (TMDb/Wikidata).
ALTER TABLE movies DROP CONSTRAINT movies_budget_confidence_check;
ALTER TABLE movies ADD CONSTRAINT movies_budget_confidence_check
    CHECK (budget_confidence = ANY (ARRAY['confirmed', 'estimated', 'unknown', 'social_estimate']));
