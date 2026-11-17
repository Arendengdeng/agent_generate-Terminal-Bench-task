FROM python:3.11-slim
RUN pip install --no-cache-dir pytest==9.2.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN mkdir -p /tests /logs/verifier /app
COPY . /tests/
WORKDIR /tests
