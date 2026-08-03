import redis
from fastapi import FastAPI
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import movies

app = FastAPI(title="FilmyBox API")
app.include_router(movies.router)


@app.get("/health")
def health():
    status = {"api": "ok", "postgres": "unreachable", "redis": "unreachable"}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["postgres"] = "ok"
    except Exception as exc:
        status["postgres"] = f"error: {exc}"

    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        status["redis"] = "ok"
    except Exception as exc:
        status["redis"] = f"error: {exc}"

    return status


@app.get("/")
def root():
    return {"message": "FilmyBox API is running"}
