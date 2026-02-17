# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies only (will be discarded)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim

# Security: run as non-root
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/

# If you have a Google service account JSON baked in (not recommended for prod;
# prefer Workload Identity or Secret Manager), uncomment the next line:
# COPY credentials.json /app/credentials.json

# Switch to non-root user
USER appuser

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080
EXPOSE ${PORT}

# Production command: gunicorn with uvicorn workers
# - workers: set to 1 for Cloud Run (each instance gets its own container)
# - timeout: 120s to cover long Gemini calls
CMD ["python", "-m", "gunicorn", \
     "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-"]
