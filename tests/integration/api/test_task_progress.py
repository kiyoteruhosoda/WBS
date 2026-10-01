"""進捗率 = 実績 ÷（実績 ＋ 残）を API で見る（task #165 / ADR-0010）。"""


def _log(client, task_id: int, hours: float) -> None:
    response = client.post("/api/work-logs", json={
        "task_id": task_id,
        "work_date": "2026-07-20",
        "hours": hours,
        "memo": None,
    })
    assert response.status_code == 201, response.text


def test_create_task_with_estimate_starts_at_zero_progress(client) -> None:
    response = client.post("/api/tasks", json={"title": "設計書レビュー", "estimated_hours": 10})
    assert response.status_code == 201
    data = response.json()
    assert data["progress_percent"] == 0.0
    assert data["remaining_hours"] == 10.0
    assert data["remaining_hours_entered"] is None


def test_create_task_without_hours_has_no_progress(client) -> None:
    # 見積も残も空なら分母 0 → null（画面は「—」）
    response = client.post("/api/tasks", json={"title": "新規タスク"})
    assert response.status_code == 201
    data = response.json()
    assert data["progress_percent"] is None
    assert data["remaining_hours"] is None


def test_worklog_drives_progress_with_default_remaining(client) -> None:
    task = client.post("/api/tasks", json={"title": "実装", "estimated_hours": 10}).json()
    _log(client, task["id"], 4)
    data = client.get(f"/api/tasks/{task['id']}").json()
    # 残が空なら 見積 − 実績 = 6h → 4 / (4 + 6) = 40%
    assert data["actual_hours"] == 4.0
    assert data["remaining_hours"] == 6.0
    assert data["progress_percent"] == 40.0


def test_overrun_task_is_not_stuck_at_100_after_remaining_is_entered(client) -> None:
    task = client.post("/api/tasks", json={"title": "超過", "estimated_hours": 5}).json()
    _log(client, task["id"], 8)
    stuck = client.get(f"/api/tasks/{task['id']}").json()
    # 残が空のままだと既定の残は 0（見積を使い切った）
    assert stuck["remaining_hours"] == 0.0

    response = client.patch(f"/api/tasks/{task['id']}", json={"remaining_hours": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["remaining_hours"] == 2.0
    assert data["remaining_hours_entered"] == 2.0
    assert data["progress_percent"] == 80.0


def test_remaining_hours_input_is_kept_on_create(client) -> None:
    response = client.post("/api/tasks", json={
        "title": "残り時間指定",
        "estimated_hours": 10,
        "remaining_hours": 3,
    })
    assert response.status_code == 201
    assert response.json()["remaining_hours"] == 3.0
    assert response.json()["remaining_hours_entered"] == 3.0


def test_sending_null_remaining_returns_to_the_default(client) -> None:
    task = client.post("/api/tasks", json={
        "title": "戻す", "estimated_hours": 10, "remaining_hours": 3,
    }).json()
    # 送らなければ触らない
    untouched = client.patch(f"/api/tasks/{task['id']}", json={"title": "戻す（改）"}).json()
    assert untouched["remaining_hours_entered"] == 3.0
    # null を送ると空へ戻り、見積 − 実績 が既定になる
    cleared = client.patch(f"/api/tasks/{task['id']}", json={"remaining_hours": None}).json()
    assert cleared["remaining_hours_entered"] is None
    assert cleared["remaining_hours"] == 10.0


def test_negative_remaining_is_rejected(client) -> None:
    response = client.post("/api/tasks", json={"title": "負", "remaining_hours": -1})
    assert response.status_code == 422


def test_zero_denominator_is_null(client) -> None:
    task = client.post("/api/tasks", json={"title": "ゼロ", "remaining_hours": 0}).json()
    assert task["progress_percent"] is None


def test_done_is_100(client) -> None:
    task = client.post("/api/tasks", json={"title": "済", "status": "DONE"}).json()
    assert task["progress_percent"] == 100.0
    assert task["remaining_hours"] == 0.0


def test_parent_rolls_up_children_everywhere(client) -> None:
    parent = client.post("/api/tasks", json={"title": "親", "estimated_hours": 100}).json()
    first = client.post("/api/tasks", json={
        "title": "子 1", "parent_task_id": parent["id"], "estimated_hours": 5, "remaining_hours": 2,
    }).json()
    second = client.post("/api/tasks", json={
        "title": "子 2", "parent_task_id": parent["id"], "estimated_hours": 5,
    }).json()
    _log(client, first["id"], 8)
    _log(client, second["id"], 1)

    # 親自身の見積（100h）は数えない。実績 8 + 1 = 9、残 2 + 4 = 6 → 60%
    data = client.get(f"/api/tasks/{parent['id']}").json()
    assert data["has_subtasks"] is True
    assert data["actual_hours"] == 0.0
    assert data["rollup_actual_hours"] == 9.0
    assert data["rollup_remaining_hours"] == 6.0
    assert data["progress_percent"] == 60.0

    # 一覧・ガントでも同じ値
    listed = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert listed[parent["id"]]["progress_percent"] == 60.0
    assert listed[first["id"]]["progress_percent"] == 80.0
    gantt = {t["id"]: t for t in client.get("/api/gantt").json()}
    assert gantt[parent["id"]]["progress_percent"] == 60.0
    assert gantt[first["id"]]["progress_percent"] == 80.0
    # 子だけに絞った一覧でも、親の積み上げは変わらない
    children = client.get(f"/api/tasks?parent_task_id={parent['id']}").json()
    assert {t["id"] for t in children} == {first["id"], second["id"]}
