def test_create_task_with_estimate_and_remaining_reports_progress(client) -> None:
    response = client.post("/api/tasks", json={
        "title": "設計書レビュー",
        "estimated_hours": 10,
        "remaining_hours": 4,
    })
    assert response.status_code == 201
    assert response.json()["progress_percent"] == 60.0


def test_create_task_without_hours_reports_zero_progress(client) -> None:
    response = client.post("/api/tasks", json={"title": "新規タスク"})
    assert response.status_code == 201
    assert response.json()["progress_percent"] == 0.0


def test_worklog_still_drives_progress(client) -> None:
    task = client.post("/api/tasks", json={
        "title": "実装",
        "estimated_hours": 10,
        "remaining_hours": 10,
    }).json()
    client.post("/api/work-logs", json={
        "task_id": task["id"],
        "work_date": "2026-07-20",
        "hours": 5,
        "memo": None,
    })
    data = client.get(f"/api/tasks/{task['id']}").json()
    # 実績5h・残り10h → 5 / 15 = 33.3%
    assert data["progress_percent"] == 33.3
