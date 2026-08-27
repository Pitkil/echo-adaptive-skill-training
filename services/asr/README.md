# ECHO ASR service

This service provides a small multilingual speech-to-text endpoint for voice answers.
It uses `Systran/faster-whisper-tiny` with CPU `int8` inference by default. The model
weights are downloaded on first transcription and stored in the `asr-model-cache`
Docker volume; they are intentionally not committed to GitHub.

Run with the main stack:

```powershell
docker compose up --build -d
```

The service listens on `http://127.0.0.1:8040` when published by Compose. ECHO uses
the internal address `http://asr:8040`. Set `ASR_MODEL_ID`, `ASR_DEVICE`, or
`ASR_COMPUTE_TYPE` in `.env` when a different model/runtime is required.

`POST /v1/asr/transcribe` accepts a multipart `audio` file and optional `language`.
The response contains the transcript and model metadata. A model download or inference
failure is returned as HTTP 503 and must be shown as a degradation, not as a transcript.
