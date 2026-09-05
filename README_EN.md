# ECHO Adaptive Skill Training

<div align="center">

<a href="README.md">中文说明</a> · <a href="LICENSE">MIT License</a>

<img src="docs/assets/readme/echo-hero.png" alt="ECHO connects learning evidence, official retrieval and adaptive coaching" width="100%">

**A conversation-first training system that turns learning evidence into an auditable next step.**

[![CI](https://github.com/Pitkil/echo-adaptive-skill-training/actions/workflows/ci.yml/badge.svg)](https://github.com/Pitkil/echo-adaptive-skill-training/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11--3.13-1d3246?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-426f62?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ed?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-3c6e71)

</div>

ECHO is an open-source, conversation-first adaptive skill-training platform. Learners interact with one ECHO assistant while the system records answers, retrieves authoritative evidence, generates learning resources, checks them, updates ability estimates and chooses the next action.

The current demonstration course is **enterprise agent development with Microsoft Semantic Kernel**. The data model supports multiple programs and modules, so course materials can be replaced with your own authorised domain content.

## Why ECHO is different

- **Evidence-centred learning** — questions, answers, video speech, server-side grading and ability changes form a reviewable learning trail.
- **Retrieval is separated from generation** — PunditRAG handles multi-route recall, RRF fusion, reranking and citations; ECHO turns evidence into a learning action.
- **Ability and behaviour stay separate** — only scorable answers update MIRT U/A/R. ASR, pauses and hesitation adjust diagnostic confidence and coaching style, not ability scores directly.
- **Auditable background collaboration** — four internal agents expose their inputs, outputs, failure reasons and final decision in Demo Trace; learners still see one assistant.
- **Fail closed** — unavailable retrieval, memory, transcription or model calls produce an explicit degraded result instead of fabricated citations, scores or ability changes.
- **One reproducible stack** — the business API, PunditRAG, SimpleMem and ASR run from the repository's Docker Compose setup.

## Learning loop

```mermaid
flowchart LR
    Q[Question, answer or voice] --> C[Read module, history, MIRT and memory]
    C --> O[TurnOrchestrator: choose one main action]
    O --> R[PunditRAG: recall official evidence]
    R --> G[Generate answer, guide, material or test]
    G --> V[Check knowledge, difficulty, answer and citations]
    V -->|pass| E[ECHO shows one response]
    V -->|fail| X[Targeted local regeneration]
    X --> V
    E --> S[Server grading and immutable turn record]
    S --> M[Update MIRT, blind spots and learning path]
    M --> O
```

Every turn has one primary action. Generated content must pass inspection; without official evidence, a resource remains a draft. PunditRAG is an evidence service, not a fifth learner-facing agent. SimpleMem stores scoped cross-session semantic memory and does not replace the business database.

## Core capabilities

| Area | What is implemented |
| --- | --- |
| Curriculum | Three modules: Kernel & plugins; agents & multi-agent collaboration; process, deployment & quality evaluation |
| ECHO orchestration | E/C/H/O state flow with one final learner-facing response |
| Adaptive diagnosis | MIRT U (understanding), A (application), R (reasoning); evidence-backed blind spots and difficulty |
| Knowledge retrieval | PunditRAG service with multi-route retrieval, hybrid vectors, RRF, reranking and traceable evidence |
| Resources | Personalised learning material, hands-on guide and stage test with checking and targeted redo |
| Assessment | Fixed pre-test, stage test, post-test and practice; server-side scoring, idempotency and optional MIRT updates |
| Multimodal input | Video checkpoints, explicit voice consent, ASR transcription and learner confirmation before scoring |
| Memory & signals | Scoped SimpleMem memory plus micro-signal integration for hesitation and pauses |
| Roles | Learner, instructor/mentor and administrator; Demo Trace exposes internal collaboration for authorised demos |

## Interface preview

<p align="center"><img src="docs/assets/readme/01-login-current.png" alt="Current ECHO login screen" width="42%"></p>
<p align="center"><sub>Current login screen captured from the running frontend.</sub></p>

<p align="center"><img src="docs/assets/readme/02-course-center.png" alt="Course center" width="49%"> <img src="docs/assets/readme/03-learning-workspace.png" alt="Learning workspace" width="49%"></p>

The learner path is intentionally short: **Course Center → an open course → modular learning → ECHO conversation and an adaptive path**. Instructors maintain authorised materials and fixed questions; administrators manage identities, configuration, service health and audit records.

## Quick start with Docker

Requirements: Docker Desktop with Compose, an LLM-compatible API key, and permission to use any imported course material. Runtime data, uploads and model caches stay outside Git.

```bash
git clone https://github.com/Pitkil/echo-adaptive-skill-training.git
cd echo-adaptive-skill-training
cp .env.example .env
# Edit .env and set the model endpoint/key and a random SIMPLEMEM_API_KEY (>=32 bytes)
docker compose up --build -d
```

Open <http://127.0.0.1:8010>. Verify the stack:

```bash
curl http://127.0.0.1:8010/api/health
docker compose ps
```

### Windows

Use Docker Desktop with the project's fixed storage policy: installation at `D:\Docker\Docker` and WSL data at `D:\DockerDesktopData`. Do not reset Docker Desktop or move the data VHDX. If the daemon is unavailable, run:

```powershell
Copy-Item .env.example .env
# Edit .env before starting the stack
powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1
docker compose up --build -d
```

### macOS

Install Docker Desktop, clone the repository, copy `.env.example` to `.env`, then run the same Compose commands. The default CPU profile works on Intel and Apple silicon. Keep Docker Desktop's virtual disk in a separately managed location with enough space for images and caches.

## Services and ports

| Service | Host endpoint | Purpose |
| --- | --- | --- |
| ECHO API and web app | `8010` | Learner, instructor and admin workflows |
| PunditRAG import | `8000` | Import authorised documents and create chunks |
| PunditRAG query | `8001` | Multi-route retrieval and evidence |
| SimpleMem | internal `8020` | Scoped long-term semantic memory; not published by default |
| Micro-signal service | `8030` | Hesitation/pause signal adapter; verify whether the deployment is Mock or real |
| ASR | `8040` | faster-whisper transcription, loaded on first use |

Useful endpoints include `GET /health`, `GET /api/health`, `POST /auth/register`, `POST /auth/login`, `GET /v1/catalog/programs`, `POST /chat` and `GET /v1/resources?module_id=<id>`. The FastAPI OpenAPI page and `docs/service-contracts.md` define the complete contracts.

The micro-signal container is an opt-in profile. Start the integration Mock only when needed with `docker compose --profile micro-mock up -d`; use the real deployment and its model licence for any production or formal accuracy claim.

## Importing your own course

Course materials and fixed quizzes are separate imports. Use authorised Microsoft Learn or repository material for the demonstration course, or replace it with material you have rights to distribute. Do not use model-generated text as the authoritative answer. Import and verify retrieval before publishing generated resources; missing evidence intentionally leaves them as drafts.

The repository includes the import and verification scripts, templates and schemas. Formal competition datasets and personal recordings are not a general benchmark and should be kept in a protected, external delivery folder.

## Privacy and safety

- Never commit `.env`, keys, passwords, databases, uploads, audio/video, model weights or personal information.
- Video playback does not open the microphone automatically. Voice checkpoints require explicit consent, transcription and learner confirmation before scoring.
- Answers and scoring rules are never returned to the client; the server grades raw submissions and protects retries with idempotency.
- SimpleMem queries are filtered by organisation and user scope; logout and identity changes clear cached unauthorised state.
- A Mock micro-signal service is for integration testing only and must not be presented as real accuracy results.

## Development and quality gates

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\quality.ps1
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
python -m compileall apps/api
docker compose config
```

See `docs/system-overview.md` for architecture, `docs/team-ownership.md` for boundaries, `docs/service-contracts.md` for API contracts and `docs/deployment-and-security.md` for production-oriented deployment. The original Chinese README remains the most detailed reference for project-specific operational notes.

## Project map

```text
apps/api/                 FastAPI app, catalog, database and orchestration
apps/api/agent/           ECHO state machine and one-action turn logic
apps/api/MIRT/            Ability estimation and learner analysis
apps/api/Quiz/            Question selection, scoring and import
apps/api/integrations/    PunditRAG, SimpleMem, micro-signal and ASR adapters
services/punditrag/       Retrieval service bundled in this repository
services/simplemem/       Scoped long-term memory service
scripts/                  Setup, migration, import and test utilities
tests/                    Unit, integration and contract tests
docs/                     Architecture, collaboration and competition notes
```

## Contributing

Please read `AGENTS.md`, `docs/collaboration.md` and `docs/testing-and-quality.md` before making changes. Keep changes scoped, add or update tests, run the quality gates, and open a focused pull request. Do not commit secrets or private evaluation data.

## License and third-party notices

The repository's original code and documentation are released under the [MIT License](LICENSE). Third-party dependencies, model weights, Microsoft documentation and repository content, and user-uploaded materials remain subject to their own licences, terms and permissions. See `models/micro_detector/LICENSE-WAVLM.txt` and the relevant dependency metadata before redistributing bundled assets.
