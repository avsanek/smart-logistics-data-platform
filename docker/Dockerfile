FROM python:3.11.11-slim-bookworm
LABEL com.smart-logistics.assignment="smart-logistics-de-test"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN /usr/local/bin/python -m pip install --no-cache-dir -r requirements.txt && /usr/local/bin/python -m pip check
COPY . .
RUN useradd --uid 50000 --create-home app && mkdir -p /app/artifacts && chown -R app:app /app
USER app
ENTRYPOINT ["/usr/local/bin/python", "-m", "etl.cli"]
CMD ["run"]
