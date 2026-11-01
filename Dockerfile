FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Cài thư viện trước để tận dụng cache layer
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

EXPOSE 8000
# Mặc định chạy API; service worker trong docker-compose ghi đè command
CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
