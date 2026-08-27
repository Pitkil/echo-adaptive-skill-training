FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

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
