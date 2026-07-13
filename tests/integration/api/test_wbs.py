from datetime import date, timedelta


def test_task_dashboard_and_dependency_cycle(client) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    first = client.post(
        "/tasks",
        json={"title": "設計レビュー", "priority": 5, "urgency": 5, "due_date": yesterday},
    )
    assert first.status_code == 201
    assert first.json()["score"] >= 1000

    second = client.post("/tasks", json={"title": "実装"})
    assert second.status_code == 201

    dep = client.post(
        "/dependencies",
        json={
            "predecessor_task_id": first.json()["id"],
            "successor_task_id": second.json()["id"],
        },
    )
    assert dep.status_code == 201

    cycle = client.post(
        "/dependencies",
        json={
            "predecessor_task_id": second.json()["id"],
            "successor_task_id": first.json()["id"],
        },
    )
    assert cycle.status_code == 409

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["kpi"]["overdue_tasks"] == 1


def test_inbox_convert_and_done_transition(client) -> None:
    inbox = client.post("/inbox", json={"title": "思いつき", "memo": "memo"})
    assert inbox.status_code == 201

    converted = client.post(f"/inbox/{inbox.json()['id']}/convert")
    assert converted.status_code == 201

    done = client.put(
        f"/tasks/{converted.json()['id']}",
        json={"title": "思いつき", "status": "DONE", "remaining_hours": 3},
    )
    assert done.status_code == 200
    assert done.json()["remaining_hours"] == 0
    assert done.json()["progress_percent"] == 100.0
