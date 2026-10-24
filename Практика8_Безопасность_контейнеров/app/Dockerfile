FROM python:3.12-slim

# Не создавать .pyc: корневая файловая система контейнера будет read-only.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Сначала зависимости: слой кэшируется, пока не изменился requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static

# Отдельный непривилегированный пользователь, а не root.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser
USER 10001:10001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:app"]
