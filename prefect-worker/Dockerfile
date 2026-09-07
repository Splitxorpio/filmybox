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

# supercronic: a cron implementation built for containers - logs straight to
# stdout (no syslog dependency) and exits nonzero on a malformed crontab,
# unlike plain cron. Used by the `scheduler` service (see docs/scheduling.md)
# to run the recurring flows on a schedule; verified against the release's
# own checksum file rather than trusting the binary download unverified.
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.49/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=e63c11a9726b775a6a11801e81af4f3fb926aa68 \
    SUPERCRONIC=supercronic-linux-amd64
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && cd /usr/local/bin \
    && curl -fsSLO "$SUPERCRONIC_URL" \
    && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
    && chmod +x "$SUPERCRONIC" \
    && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["python", "worker_entrypoint.py"]
