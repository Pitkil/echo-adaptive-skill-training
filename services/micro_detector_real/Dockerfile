FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    MICRO_DETECTOR_OFFLINE_MODE=true \
    MICRO_MODEL_ROOT=/models

WORKDIR /workspace

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY services/micro_detector_real/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/micro_detector_real /workspace/services/micro_detector_real

EXPOSE 8030

CMD ["uvicorn", "services.micro_detector_real.app:app", "--host", "0.0.0.0", "--port", "8030"]
