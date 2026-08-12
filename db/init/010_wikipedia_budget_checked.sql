-- Tracks which movies have been *definitively* checked against Wikipedia's
-- infobox for a budget (found, no article exists, or article has no USD
-- budget field) vs. merely rate-limited-and-never-resolved. Without this,
-- budget_wikipedia_backfill.py re-runs re-scan the same already-failed
-- movies indefinitely (confirmed this session: two re-runs processed 971
-- movies combined and matched 0, since the first run had already covered
-- nearly the whole backlog).
ALTER TABLE movies ADD COLUMN wikipedia_budget_checked BOOLEAN NOT NULL DEFAULT false;
