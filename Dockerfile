# Dockerfile — Shadowbox Web API + Frontend
#
# Multi-stage build:
#   Stage 1: Build React frontend
#   Stage 2: Python runtime with FastAPI
#
# BUILD:  docker build -t shadowbox:latest .
# RUN:    docker run -p 7799:7799 --env-file .env shadowbox:latest

# ── Stage 1: Build frontend ──────────────────────────────────────
FROM node:22-alpine AS frontend

WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --production=false

COPY web/ ./
RUN npm run build

# ── Stage 2: Python runtime ──────────────────────────────────────
FROM python:3.13-slim AS runtime

# System dependencies for enrichment scripts
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    dnsutils \
    whois \
    nmap \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

# Copy application code
COPY core/ ./core/
COPY web/api/ ./web/api/
COPY web/__init__.py ./web/
COPY scripts/ ./scripts/
COPY workspaces/ ./workspaces/
COPY config/openclaw.json.template ./config/
COPY tests/mocks/ ./tests/mocks/

# Copy built frontend from stage 1
COPY --from=frontend /app/web/dist ./web/dist/

# Create data directories
RUN mkdir -p data/feeds data/cache data/faiss data/investigations data/reports

# Environment defaults
ENV HOOK_DIR=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=7799

EXPOSE 7799

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:7799/api/status || exit 1

CMD ["python3", "-m", "uvicorn", "web.api.server:app", "--host", "0.0.0.0", "--port", "7799"]
