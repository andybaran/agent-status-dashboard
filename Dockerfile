# Agent Status Dashboard
# Multi-stage build for minimal image size

FROM python:3.13-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/build/deps -r requirements.txt

FROM python:3.13-slim

# Create non-root user
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /build/deps /usr/local/lib/python3.13/site-packages

# Copy application
COPY dashboard.py .

# Create data directory for database mount
RUN mkdir -p /data && chown appuser:appuser /data

# Switch to non-root user
USER appuser

# Environment defaults
ARG APP_VERSION=dev
ENV DASHBOARD_PORT=5050
ENV DB_PATH=/data/agent_status.db
ENV CSV_PATH=/data/agent_status.csv
ENV DASHBOARD_TITLE="Agent Status Dashboard"
ENV APP_VERSION=${APP_VERSION}

EXPOSE 5050

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5050/api/status')" || exit 1

CMD ["python", "dashboard.py"]
