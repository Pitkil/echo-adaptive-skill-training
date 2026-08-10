# Micro detector development service

This directory provides the lightweight, contract-compatible mock service for the external
micro-representation detector. It is intentionally isolated from the ECHO API dependencies and
does not contain WavLM, FAISS, model weights, indexes, audio, or code copied from SpeechProject.

Start ECHO and the mock detector:

```powershell
docker compose --profile micro-mock up --build
```

The mock service listens on `http://127.0.0.1:8030`. Its `/health` response always identifies
`mode` as `mock`; its deterministic hesitation event is for contract integration only and must
not be treated as a real analysis result. Run `docker compose up --build` without the profile to
start ECHO alone and exercise the documented external-service degradation path.

The future real detector must keep the same `/v1/detection/jobs` contract, use separate heavy
dependencies and external model/index volumes, and must never write directly to the ECHO database.
Multipart requests use the `audio` file field. Detector responses and events use `job_id` only for
the detector-generated identifier; ECHO's internal job identifier is carried separately as the
request `trace_id` and must not replace the detector identifier in event payloads.
