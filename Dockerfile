FROM python:3.10-slim

# System deps:
#   libqpdf-dev  — required by pikepdf (PDF password-protect + manipulation)
#   libpq-dev    — needed if psycopg2 source build ever replaces binary wheel
#   gcc          — compile fallback for any C-ext wheels not available as binary
RUN apt-get update && apt-get install -y --no-install-recommends \
        libqpdf-dev \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying code so Docker caches the layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fallback local media dir — only used when T3_ACCESS_KEY_ID is not set (dev mode)
RUN mkdir -p /app/media

EXPOSE 8000

# migrate runs as part of the release step (see docker-compose command override).
# Default entrypoint: production WSGI server.
CMD ["gunicorn", "hr_api.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--timeout", "120"]
