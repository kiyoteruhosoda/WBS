def test_create_task_with_estimate_starts_at_zero_progress(client) -> None:
    response = client.post("/api/tasks", json={"title": "設計書レビュー", "estimated_hours": 10})
    assert response.status_code == 201
    data = response.json()
    assert data["progress_percent"] == 0.0
    assert data["remaining_hours"] == 10.0


def test_create_task_without_hours_reports_zero_progress(client) -> None:
    response = client.post("/api/tasks", json={"title": "新規タスク"})
    assert response.status_code == 201
    data = response.json()
    assert data["progress_percent"] == 0.0
    assert data["remaining_hours"] is None


def test_worklog_drives_progress_and_remaining(client) -> None:
    task = client.post("/api/tasks", json={"title": "実装", "estimated_hours": 10}).json()
    client.post("/api/work-logs", json={
        "task_id": task["id"],
        "work_date": "2026-07-20",
        "hours": 4,
        "memo": None,
    })
    data = client.get(f"/api/tasks/{task['id']}").json()
    # 実績4h / 見積10h → 40%、残り = 10 - 4 = 6h
    assert data["progress_percent"] == 40.0
    assert data["remaining_hours"] == 6.0


def test_actual_exceeding_estimate_caps_progress(client) -> None:
    task = client.post("/api/tasks", json={"title": "超過", "estimated_hours": 5}).json()
    client.post("/api/work-logs", json={
        "task_id": task["id"],
        "work_date": "2026-07-20",
        "hours": 8,
        "memo": None,
    })
    data = client.get(f"/api/tasks/{task['id']}").json()
    assert data["progress_percent"] == 100.0
    assert data["remaining_hours"] == 0.0


def test_remaining_hours_input_is_ignored(client) -> None:
    # 残り時間は入力不可（送っても無視され、見積−実績で計算される）
    response = client.post("/api/tasks", json={
        "title": "残り時間指定",
        "estimated_hours": 10,
        "remaining_hours": 3,
    })
    assert response.status_code == 201
    assert response.json()["remaining_hours"] == 10.0
