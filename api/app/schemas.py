from datetime import date, datetime

from pydantic import BaseModel


class UserRegisterIn(BaseModel):
    email: str
    password: str


class UserLoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str


class StudioOut(BaseModel):
    id: int
    name: str


class FranchiseOut(BaseModel):
    id: int
    name: str


class CreditOut(BaseModel):
    person_id: int
    name: str
    role_type: str
    billing_order: int | None
    character_name: str | None


class BoxOfficeTotalsOut(BaseModel):
    opening_weekend_domestic: int | None
    total_domestic: int | None
    total_international: int | None
    total_worldwide: int | None


class BoxOfficeWeeklyOut(BaseModel):
    weekend_number: int
    weekend_gross: int | None
    theater_count: int | None


class CriticScoresOut(BaseModel):
    imdb_rating: float | None
    imdb_votes: int | None
    rotten_tomatoes_pct: int | None
    metacritic_score: int | None
    tmdb_vote_average: float | None = None
    tmdb_vote_count: int | None = None


class MovieSummary(BaseModel):
    id: int
    title: str
    release_date: date | None
    genres: list[str]
    mpaa_rating: str | None
    budget_usd: int | None
    studio_name: str | None
    total_worldwide: int | None
    poster_path: str | None


class MovieListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[MovieSummary]


class MovieDetail(BaseModel):
    id: int
    title: str
    release_date: date | None
    genres: list[str]
    runtime_minutes: int | None
    mpaa_rating: str | None
    original_language: str | None
    budget_usd: int | None
    budget_confidence: str
    poster_path: str | None
    studio: StudioOut | None
    franchise: FranchiseOut | None
    credits: list[CreditOut]
    box_office_totals: BoxOfficeTotalsOut | None
    box_office_weekly: list[BoxOfficeWeeklyOut]
    critic_scores: CriticScoresOut | None


class CompOut(BaseModel):
    movie_id: int
    title: str
    release_date: date | None
    shared_genres: list[str] = []
    score: int | None = None
    distance: float | None = None


class VerdictOut(BaseModel):
    stage: str
    computed_at: datetime
    comp_count: int
    roi_multiple_p25: float | None
    roi_multiple_p50: float | None
    roi_multiple_p75: float | None
    verdict_bucket: str | None
    comp_movie_ids: list[int]
    actual_roi_multiple: float | None
    actual_bucket: str | None
    method: str


class SentimentSnapshotOut(BaseModel):
    source: str
    stage: str
    snapshot_date: datetime
    sentiment_score: float | None
    volume: int | None
    avg_engagement_score: float | None


class LivePredictionOut(BaseModel):
    roi_multiple_p25: float | None
    roi_multiple_p50: float | None
    roi_multiple_p75: float | None
    verdict_bucket: str | None
    method: str
    computed_at: datetime
    reason: str | None = None
