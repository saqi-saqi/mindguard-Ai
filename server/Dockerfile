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

# Copy dependencies list and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY . .

# Expose Flask API port
EXPOSE 5000

# Non-root user safety
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run Flask backend REST server
CMD ["python", "app.py"]
