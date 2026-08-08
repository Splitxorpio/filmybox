FROM python:3.12-slim

WORKDIR /app

# libgomp1: LightGBM's compiled backend links against libgomp at runtime and
# the slim base image doesn't ship it.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install a CPU-only torch build first, from PyTorch's own CPU wheel index -
# otherwise pip resolves the default GPU/CUDA build via sentence-transformers'
# torch dependency, pulling several GB of unused nvidia-* CUDA packages into
# a container that only ever runs on CPU.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "worker_entrypoint.py"]
