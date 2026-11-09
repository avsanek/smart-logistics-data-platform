FROM apache/airflow:2.10.5-python3.11
LABEL com.smart-logistics.assignment="smart-logistics-de-test"
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client libgomp1 && rm -rf /var/lib/apt/lists/*
USER airflow
COPY requirements.txt /tmp/project-requirements.txt
RUN pip install --no-cache-dir 'apache-airflow==2.10.5' -r /tmp/project-requirements.txt && pip check
WORKDIR /app
COPY --chown=airflow:root . /app
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
