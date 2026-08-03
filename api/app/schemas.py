from datetime import date

from pydantic import BaseModel


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


class MovieSummary(BaseModel):
    id: int
    title: str
    release_date: date | None
    genres: list[str]
    mpaa_rating: str | None
    budget_usd: int | None
    studio_name: str | None
    total_worldwide: int | None


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
    studio: StudioOut | None
    franchise: FranchiseOut | None
    credits: list[CreditOut]
    box_office_totals: BoxOfficeTotalsOut | None
    box_office_weekly: list[BoxOfficeWeeklyOut]


class CompOut(BaseModel):
    movie_id: int
    title: str
    release_date: date | None
    shared_genres: list[str]
    score: int
