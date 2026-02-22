from fastapi.testclient import TestClient

from app import app


def test_alpha_self_play_dispatches_all_providers() -> None:
    with TestClient(app) as client:
        create = client.post(
            "/v1/tasks",
            json={
                "title": "oauth milestone",
                "objective": "simulate task decomposition",
                "subtasks": [
                    "design instruction lifecycle",
                    "build oauth invite endpoint",
                    "build token exchange endpoint",
                    "add audit logging",
                    "write docs",
                    "run integration tests",
                ],
                "agent_alpha": {"claude": 0.4, "codex": 0.35, "gemini": 0.25},
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        dispatch = client.post(f"/v1/tasks/{task_id}/dispatch")
        assert dispatch.status_code == 200
        counts = dispatch.json()["assignments"]

        # self-play across each alpha provider
        assert set(counts) == {"claude", "codex", "gemini"}
        assert sum(counts.values()) == 6

        for provider in ["claude", "codex", "gemini"]:
            msg = client.post(
                "/v1/messages",
                json={
                    "task_id": task_id,
                    "channel": f"task:{task_id}",
                    "sender": provider,
                    "message_type": "status",
                    "content": f"{provider} completed assigned subtasks",
                },
            )
            assert msg.status_code == 200
