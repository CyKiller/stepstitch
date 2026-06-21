# StepStitch ingest API — the deployable host (docs/DEPLOY.md, PRODUCT-PLAN A).
# Mounts create_stepstitch_router into FastAPI and serves it with uvicorn.
# (The MCP connector has its own image: service/Dockerfile.mcp.)
# Base image: python:3.11-slim pinned by digest for reproducible builds.
# To refresh: `docker buildx imagetools inspect python:3.11-slim` → copy the top-level
# (multi-arch index) Digest, not a per-platform child digest, so CI keeps a portable pin.
FROM python:3.11-slim@sha256:ae52c5bef62a6bdd42cd1e8dffef86b9cd284bde9427da79839de7a4b983e7ca

WORKDIR /app

# Install the open-core service (brings fastapi + pydantic), then the host's extras.
COPY service/ ./service/
RUN pip install --no-cache-dir ./service
COPY server/ ./server/
RUN pip install --no-cache-dir -r server/requirements.txt

ENV STEPSTITCH_PROFILE=financial-services-enterprise

# Run as an unprivileged user (installs above ran as root; /app stays root-readable).
RUN useradd --create-home --uid 10001 stepstitch
USER stepstitch

# Probe /healthz using Python stdlib (the slim image has no curl).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+(os.environ.get('PORT') or '8000')+'/healthz').status==200 else 1)"

# Railway injects $PORT; bind to it (fallback 8000 for local runs).
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 25"]
