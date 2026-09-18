FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0

# Install ca-certificates and curl for health probes
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Run as non-root user
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -s /bin/bash appuser

WORKDIR /app

# Copy application manifests and code
COPY --chown=appuser:appuser pyproject.toml alembic.ini ./
COPY --chown=appuser:appuser docs/STATE.md docs/SOURCE_REGISTRY.yaml docs/
COPY --chown=appuser:appuser api api
COPY --chown=appuser:appuser core core
COPY --chown=appuser:appuser feedback feedback
COPY --chown=appuser:appuser inbox inbox
COPY --chown=appuser:appuser matching matching
COPY --chown=appuser:appuser opportunity opportunity
COPY --chown=appuser:appuser outbound outbound
COPY --chown=appuser:appuser recon recon
COPY --chown=appuser:appuser security security
COPY --chown=appuser:appuser storage storage
COPY --chown=appuser:appuser truth truth
COPY --chown=appuser:appuser worker worker
COPY --chown=appuser:appuser scripts scripts

# Deterministically install production dependencies from pyproject.toml
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Prepare output directory owned by appuser
RUN mkdir -p /app/out && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["python", "scripts/container_entrypoint.py"]
CMD ["api"]
