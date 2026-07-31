from prefect import flow, task


@task
def check_env() -> dict:
    import os

    return {
        "tmdb_key_set": bool(os.getenv("TMDB_API_KEY")),
        "youtube_key_set": bool(os.getenv("YOUTUBE_API_KEY")),
    }


@flow(name="filmybox-scaffold-healthcheck")
def healthcheck_flow():
    return check_env()


if __name__ == "__main__":
    print(healthcheck_flow())
