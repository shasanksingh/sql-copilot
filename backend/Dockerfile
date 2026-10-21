FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend ./backend
COPY agentic ./agentic
COPY rl ./rl
COPY main.py ./main.py
COPY spider_text_sql.csv ./spider_text_sql.csv

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.runtime \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:asgi_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]