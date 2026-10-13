"""タスクを消す・しまう（task #388 / ADR-0046）。打刻や実績があれば消さずにしまう。"""

from __future__ import annotations

from datetime import timedelta

from src.shared.clock import utcnow


def _task(client, title: str) -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _z(value) -> str:
    return f"{value.replace(microsecond=0).isoformat()}Z"


def _entry(client, task_id: int, hours_ago: int, minutes: int) -> None:
    start = utcnow() - timedelta(hours=hours_ago)
    res = client.post(
        "/api/time-entries",
        json={"started_at": _z(start), "ended_at": _z(start + timedelta(minutes=minutes)), "task_id": task_id},
    )
    assert res.status_code == 201, res.text


def _rule(client, task_id: int, app: str) -> int:
    res = client.post("/api/tracking-rules", json={"app": app, "task_id": task_id})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _listed(client) -> set[int]:
    return {t["id"] for t in client.get("/api/tasks").json()}


def test_a_task_without_time_entries_is_deleted(client) -> None:
    task = _task(client, "資料の下書き")
    _rule(client, task, "WINWORD.EXE")
    preview = client.get(f"/api/tasks/{task}/removal").json()
    assert preview == {
        "task_id": task, "title": "資料の下書き", "action": "delete", "time_entries": 0,
        "tracked_seconds": 0, "work_log_hours": 0.0, "tracking_rules": 1, "blocked_by": None,
        "archived": False,
    }
    assert client.delete(f"/api/tasks/{task}").status_code == 204
    assert client.get(f"/api/tasks/{task}").status_code == 404
    assert task not in _listed(client)


def test_a_task_with_time_entries_is_archived_not_deleted(client) -> None:
    task = _task(client, "見積書を作る")
    other = _task(client, "続く")
    _entry(client, task, 5, 30)
    _entry(client, task, 3, 60)
    rule = _rule(client, task, "EXCEL.EXE")
    _rule(client, task, "OUTLOOK.EXE")
    kept_rule = _rule(client, other, "Code.exe")

    preview = client.get(f"/api/tasks/{task}/removal").json()
    assert (preview["action"], preview["time_entries"], preview["tracked_seconds"], preview["tracking_rules"]) == (
        "archive", 2, 90 * 60, 2,
    )
    # 消せない（締めた期間や実績の名前が消えるので）
    assert client.delete(f"/api/tasks/{task}").status_code == 409
    assert client.post(f"/api/tasks/{task}/archive").status_code == 204
    assert client.post(f"/api/tasks/{task}/archive").status_code == 204  # 冪等

    # 一覧・ガント・付け替え先に出ない
    assert task not in _listed(client) and other in _listed(client)
    assert task not in {t["id"] for t in client.get("/api/gantt").json()}
    assert task not in {t["id"] for t in client.get("/api/tracking-rules/tasks").json()["tasks"]}
    # 1 件の取得では返る（しまった印つき）
    detail = client.get(f"/api/tasks/{task}").json()
    assert detail["archived_at"] is not None
    assert client.get(f"/api/tasks/{task}/removal").json()["archived"] is True
    # 規則は止まる（PC へ渡らない。画面では使われていないと出る）
    assert [r["id"] for r in client.get("/api/tracking-rules").json()["rules"]] == [kept_rule]
    editor = {r["id"]: r for r in client.get("/api/tracking-rules/editor").json()}
    assert (editor[rule]["task_available"], editor[rule]["task_title"]) == (False, "見積書を作る")
    # 打刻にはタスクの名前が残る
    start = utcnow() - timedelta(hours=6)
    entries = client.get("/api/time-entries", params={"start": _z(start), "end": _z(utcnow())}).json()
    assert {e["task_title"] for e in entries} == {"見積書を作る"}


def test_a_task_with_only_work_logs_is_archived(client) -> None:
    task = _task(client, "手で付けた実績")
    res = client.post("/api/work-logs", json={"task_id": task, "work_date": "2026-10-01", "hours": "1.5"})
    assert res.status_code == 201, res.text
    preview = client.get(f"/api/tasks/{task}/removal").json()
    assert (preview["action"], preview["time_entries"], preview["work_log_hours"]) == ("archive", 0, 1.5)
    assert client.delete(f"/api/tasks/{task}").status_code == 409


def test_a_task_being_timed_is_neither_deleted_nor_archived(client) -> None:
    task = _task(client, "計測中")
    assert client.post("/api/time-entries/start", json={"task_id": task}).status_code == 201
    assert client.get(f"/api/tasks/{task}/removal").json()["blocked_by"] == "running"
    assert client.delete(f"/api/tasks/{task}").status_code == 409
    assert client.post(f"/api/tasks/{task}/archive").status_code == 409
    client.post("/api/time-entries/stop")
    assert client.post(f"/api/tasks/{task}/archive").status_code == 204


def test_rules_cannot_point_to_an_archived_task(client) -> None:
    task = _task(client, "しまう")
    _entry(client, task, 2, 10)
    client.post(f"/api/tasks/{task}/archive")
    assert client.post("/api/tracking-rules", json={"app": "a.exe", "task_id": task}).status_code == 422
