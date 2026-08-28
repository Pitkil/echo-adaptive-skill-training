FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ASR_MODEL_ID=Systran/faster-whisper-tiny \
    ASR_DEVICE=cpu \
    ASR_COMPUTE_TYPE=int8 \
    ASR_DOWNLOAD_ROOT=/models

WORKDIR /service

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app.py ./

RUN useradd --create-home --uid 10001 asr \
    && mkdir -p /models /tmp/asr \
    && chown -R asr:asr /models /tmp/asr
USER asr

EXPOSE 8040
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8040/health', timeout=3)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8040"]
