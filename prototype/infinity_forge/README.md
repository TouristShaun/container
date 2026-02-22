# Infinity Forge MVP (from `docs/ai-pair-programming-platform-design.md`)

This is a scoped implementation of the design doc using:
- **FastAPI** for the API surface.
- **SQLite** for persistence.
- **Docker** via `Dockerfile` + `docker-compose.yml`.

## Implemented pieces
- `POST /v1/tasks` — create task + subtasks + alpha config.
- `POST /v1/tasks/{id}/dispatch` — alpha-weighted subtask allocation (`claude`, `codex`, `gemini`).
- `GET /v1/tasks/{id}/assignments` — inspect assignments.
- `POST /v1/messages` — platform-native task channel messages.
- `GET /healthz` — health endpoint.

## Run locally
```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

## Run in Docker
```bash
docker compose up --build
```

## Test (self-play for each alpha)
```bash
pytest -q
```

The test creates one task, dispatches subtasks with alpha scheduling, and posts one message from each provider (`claude`, `codex`, `gemini`) to validate end-to-end flow.
