FROM python:3.12-slim

WORKDIR /app

# libgomp1: LightGBM's compiled backend links against libgomp at runtime and
# the slim base image doesn't ship it (same issue hit in prefect-worker).
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
