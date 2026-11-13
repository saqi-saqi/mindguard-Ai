# MindGuard Backend API Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Prevent Python from writing bytecode and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency lists and install
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt

# Copy backend source code
COPY . .

# Expose Flask API port
EXPOSE 5000

# Non-root user safety
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Production WSGI server. Single worker is REQUIRED, not a shortcut:
# the sliding-window rate limiter, 15-minute cross-turn session safety
# context, user cooling windows and the safety-log circuit breaker are all
# in-process state. Horizontal scaling needs Redis-backed stores first
# (see docs/ARCHITECTURE.md). Threads absorb concurrent requests.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "60", "--preload", "--bind", "0.0.0.0:5000", "app:app"]
