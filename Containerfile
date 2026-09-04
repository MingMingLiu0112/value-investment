FROM docker.io/library/python:3.12-slim

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY sql ./sql
COPY src ./src

RUN pip install --no-cache-dir .

CMD ["python", "-m", "value_investment_agent"]
