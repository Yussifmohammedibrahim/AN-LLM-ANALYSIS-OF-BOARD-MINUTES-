# Dockerfile for ITDS Backend & Worker
FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for OCR and Audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy backend codebase
COPY run.py .
COPY run_worker.py .
COPY scripts/ ./scripts/
COPY itds_env/ ./itds_env/

# Create directories for persistent data (sqlite database and file uploads)
RUN mkdir -p /data/uploads && chmod -R 777 /data
RUN ln -s /data/uploads /app/uploads

# Default production configurations
ENV ITDS_DB_PATH=/data/itds_minutes.db
ENV TESSERACT_CMD=/usr/bin/tesseract
ENV FFMPEG_CMD=/usr/bin/ffmpeg
ENV PYTHONPATH=/app/itds_env

# Expose backend port
EXPOSE 5001

# Default execution command (will be overridden for the worker in docker-compose)
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--timeout", "300", "app.app:app"]
