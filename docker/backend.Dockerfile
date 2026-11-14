# EnergiQ AI API image. Build from the repository root:  docker build -f docker/backend.Dockerfile -t energiq-api .
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMP_NUM_THREADS=2

# libgomp1 is required by XGBoost / scikit-learn OpenMP code.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 energiq

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY backend ./backend
COPY ml_engine ./ml_engine
COPY data/sample ./data/sample
COPY artifacts/reports ./artifacts/reports
# Society (multi-building community) module: the processed BDG2 communities that "Import bundled communities" loads into the database, and the
# trained evaluation files / deployed models that go with them (read-only here; the entrypoint copies the artifacts onto the /data volume once).
COPY data/society/processed ./data/society/processed
COPY artifacts/society ./artifacts/society
COPY docker/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh

# Writable state lives under /data (mount a volume there). Everything else is read-only application code.
RUN mkdir -p /data/uploads /data/models /data/society && chown -R energiq:energiq /data \
    && chmod +x /usr/local/bin/backend-entrypoint.sh

ENV ENERGIQ_ENV=prod \
    ENERGIQ_UPLOAD_DIR=/data/uploads \
    ENERGIQ_MODELS_DIR=/data/models \
    ENERGIQ_REPORTS_DIR=/app/artifacts/reports \
    ENERGIQ_SOCIETY_DATA_DIR=/app/data/society/processed \
    ENERGIQ_SOCIETY_DIR=/data/society \
    SOCIETY_SEED_DIR=/app/artifacts/society \
    ENERGIQ_SAMPLE_DATASET=/app/data/sample/uci_hourly_2009_sample.csv

USER energiq
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).status == 200 else 1)"

# The rate limiter and job runner keep state in-process, so run exactly ONE worker per container.
ENTRYPOINT ["backend-entrypoint.sh"]
CMD ["uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
