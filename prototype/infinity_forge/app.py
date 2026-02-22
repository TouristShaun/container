from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass
from math import floor
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.getenv("INFINITY_FORGE_DB", "/data/infinity_forge.db")


@dataclass(frozen=True)
class AgentWeight:
    provider: str
    weight: float


DEFAULT_ALPHA = {
    "claude": 0.40,
    "codex": 0.35,
    "gemini": 0.25,
}


class TaskCreateRequest(BaseModel):
    title: str
    objective: str
    subtasks: list[str] = Field(default_factory=list)
    agent_alpha: dict[str, float] | None = None


class MessageCreateRequest(BaseModel):
    task_id: str
    channel: str
    sender: str
    message_type: str
    content: str


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                status TEXT NOT NULL,
                alpha_config_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS subtasks (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                body TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );

            CREATE TABLE IF NOT EXISTS task_assignments (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                subtask_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                override_reason TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(id),
                FOREIGN KEY(subtask_id) REFERENCES subtasks(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                sender TEXT NOT NULL,
                message_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            """
        )


def normalize_alpha(agent_alpha: dict[str, float] | None) -> list[AgentWeight]:
    merged = dict(DEFAULT_ALPHA)
    if agent_alpha:
        merged.update(agent_alpha)
    if any(value < 0 for value in merged.values()):
        raise ValueError("alpha values cannot be negative")

    total = sum(merged.values())
    if total == 0:
        raise ValueError("alpha sum cannot be zero")

    return [AgentWeight(provider=provider, weight=value / total) for provider, value in merged.items()]


def allocate_subtasks(subtask_ids: list[str], weights: list[AgentWeight]) -> dict[str, str]:
    if not subtask_ids:
        return {}

    n = len(subtask_ids)
    raw_targets = {item.provider: item.weight * n for item in weights}
    assigned = {provider: floor(target) for provider, target in raw_targets.items()}
    leftovers = n - sum(assigned.values())

    by_remainder = sorted(
        ((provider, raw_targets[provider] - assigned[provider]) for provider in assigned),
        key=lambda item: item[1],
        reverse=True,
    )

    for provider, _ in by_remainder[:leftovers]:
        assigned[provider] += 1

    allocation: dict[str, str] = {}
    cursor = 0
    for provider in sorted(assigned):
        for _ in range(assigned[provider]):
            allocation[subtask_ids[cursor]] = provider
            cursor += 1

    return allocation


app = FastAPI(title="Infinity Forge MVP")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.post("/v1/tasks")
def create_task(payload: TaskCreateRequest) -> dict[str, Any]:
    try:
        normalized = normalize_alpha(payload.agent_alpha)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task_id = str(uuid.uuid4())
    subtask_ids = [str(uuid.uuid4()) for _ in payload.subtasks]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tasks(id, title, objective, status, alpha_config_json) VALUES(?, ?, ?, ?, ?)",
            (task_id, payload.title, payload.objective, "created", json.dumps([w.__dict__ for w in normalized])),
        )
        conn.executemany(
            "INSERT INTO subtasks(id, task_id, body) VALUES(?, ?, ?)",
            list(zip(subtask_ids, [task_id] * len(subtask_ids), payload.subtasks, strict=False)),
        )

    return {
        "task_id": task_id,
        "status": "created",
        "alpha": [w.__dict__ for w in normalized],
        "subtask_count": len(subtask_ids),
    }


@app.post("/v1/tasks/{task_id}/dispatch")
def dispatch_task(task_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        subtasks = conn.execute("SELECT id FROM subtasks WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()
        weights = [AgentWeight(**item) for item in json.loads(task["alpha_config_json"])]
        allocation = allocate_subtasks([row["id"] for row in subtasks], weights)

        conn.execute("DELETE FROM task_assignments WHERE task_id = ?", (task_id,))
        conn.executemany(
            "INSERT INTO task_assignments(id, task_id, subtask_id, provider, override_reason) VALUES(?, ?, ?, ?, ?)",
            [
                (str(uuid.uuid4()), task_id, subtask_id, provider, None)
                for subtask_id, provider in allocation.items()
            ],
        )
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", ("dispatched", task_id))

    provider_counts: dict[str, int] = defaultdict(int)
    for provider in allocation.values():
        provider_counts[provider] += 1

    return {"task_id": task_id, "status": "dispatched", "assignments": provider_counts}


@app.get("/v1/tasks/{task_id}/assignments")
def list_assignments(task_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT subtask_id, provider FROM task_assignments WHERE task_id = ? ORDER BY subtask_id", (task_id,)
        ).fetchall()

    return {"task_id": task_id, "assignments": [dict(row) for row in rows]}


@app.post("/v1/messages")
def post_message(payload: MessageCreateRequest) -> dict[str, str]:
    message_id = str(uuid.uuid4())
    with get_conn() as conn:
        task = conn.execute("SELECT 1 FROM tasks WHERE id = ?", (payload.task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        conn.execute(
            "INSERT INTO messages(id, task_id, channel, sender, message_type, content) VALUES(?, ?, ?, ?, ?, ?)",
            (
                message_id,
                payload.task_id,
                payload.channel,
                payload.sender,
                payload.message_type,
                payload.content,
            ),
        )
    return {"message_id": message_id, "status": "accepted"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
