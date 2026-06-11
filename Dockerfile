# StepStitch ingest API — the deployable host (docs/DEPLOY.md, PRODUCT-PLAN A).
# Mounts create_stepstitch_router into FastAPI and serves it with uvicorn.
# (The MCP connector has its own image: service/Dockerfile.mcp.)
FROM python:3.11-slim

WORKDIR /app

# Install the open-core service (brings fastapi + pydantic), then the host's extras.
COPY service/ ./service/
RUN pip install --no-cache-dir ./service
COPY server/ ./server/
RUN pip install --no-cache-dir -r server/requirements.txt

ENV STEPSTITCH_PROFILE=financial-services-enterprise

# Railway injects $PORT; bind to it (fallback 8000 for local runs).
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
