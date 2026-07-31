from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://filmybox:filmybox@postgres:5432/filmybox"
    redis_url: str = "redis://redis:6379/0"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
