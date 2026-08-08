-- Widen the verdicts uniqueness constraint so multiple prediction methods
-- (comp_heuristic_v1, gbt_v1, ...) can coexist for the same movie/stage.
ALTER TABLE verdicts DROP CONSTRAINT verdicts_movie_id_stage_key;
ALTER TABLE verdicts ADD CONSTRAINT verdicts_movie_id_stage_method_key UNIQUE (movie_id, stage, method);
