FROM python:3.12-slim

WORKDIR /app

# Install a CPU-only torch build first, from PyTorch's own CPU wheel index -
# otherwise pip resolves the default GPU/CUDA build via sentence-transformers'
# torch dependency, pulling several GB of unused nvidia-* CUDA packages into
# a container that only ever runs on CPU.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "worker_entrypoint.py"]
