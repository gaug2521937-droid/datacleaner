# DataCleaner — серверная версия. Используется на Render/Fly/любом Docker-хосте.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATACLEANER_DB=/data/datacleaner.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# На бесплатных тарифах диск не постоянный: каталог /data создаётся на лету,
# данные живут до перезапуска инстанса. Для постоянного хранения задайте
# DATACLEANER_DB на смонтированный volume.
RUN mkdir -p /data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
