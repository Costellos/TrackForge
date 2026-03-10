FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2, pyacoustid
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libchromaprint-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "trackforge.main:app", "--host", "0.0.0.0", "--port", "8080"]
