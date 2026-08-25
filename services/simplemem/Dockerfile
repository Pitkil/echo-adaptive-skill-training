FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SIMPLEMEM_HOST=0.0.0.0 \
    SIMPLEMEM_PORT=8020 \
    SIMPLEMEM_DB_PATH=/data/simplemem.db \
    SIMPLEMEM_ALLOW_INSECURE_DEV=false

WORKDIR /service

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY simplemem ./simplemem

RUN mkdir -p /data && chown -R 10001:10001 /service /data
USER 10001:10001

EXPOSE 8020
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8020/health', timeout=2)"

CMD ["python", "-m", "simplemem"]
