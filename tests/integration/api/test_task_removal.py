"""タスクを消す・アーカイブする（task #388 / ADR-0046）。確定した実績があれば消さずにアーカイブする。

打刻と WinTrack の規則は Tracker へ移したので、ここでは見ない（task #543 / ADR-0070）。
"""

from __future__ import annotations


def _task(client, title: str) -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _work_log(client, task_id: int, hours: str) -> None:
    res = client.post("/api/work-logs", json={"task_id": task_id, "work_date": "2026-10-01", "hours": hours})
    assert res.status_code == 201, res.text


def _listed(client) -> set[int]:
    return {t["id"] for t in client.get("/api/tasks").json()}


def test_a_task_without_work_logs_is_deleted(client) -> None:
    task = _task(client, "資料の下書き")
    preview = client.get(f"/api/tasks/{task}/removal").json()
    assert preview == {
        "task_id": task, "title": "資料の下書き", "action": "delete", "work_log_hours": 0.0, "archived": False,
    }
    assert client.delete(f"/api/tasks/{task}").status_code == 204
    assert client.get(f"/api/tasks/{task}").status_code == 404
    assert task not in _listed(client)


def test_a_task_with_work_logs_is_archived_not_deleted(client) -> None:
    task = _task(client, "見積書を作る")
    other = _task(client, "続く")
    _work_log(client, task, "1.5")

    preview = client.get(f"/api/tasks/{task}/removal").json()
    assert (preview["action"], preview["work_log_hours"]) == ("archive", 1.5)
    # 消せない（実績の表から名前が消えるので）
    assert client.delete(f"/api/tasks/{task}").status_code == 409
    assert client.post(f"/api/tasks/{task}/archive").status_code == 204
    assert client.post(f"/api/tasks/{task}/archive").status_code == 204  # 冪等

    # 一覧・ガントに出ない
    assert task not in _listed(client) and other in _listed(client)
    assert task not in {t["id"] for t in client.get("/api/gantt").json()}
    # 1 件の取得では返る（アーカイブの印つき）
    detail = client.get(f"/api/tasks/{task}").json()
    assert detail["archived_at"] is not None
    assert client.get(f"/api/tasks/{task}/removal").json()["archived"] is True


def test_a_task_without_work_logs_can_still_be_archived(client) -> None:
    task = _task(client, "とりあえずアーカイブ")
    assert client.post(f"/api/tasks/{task}/archive").status_code == 204
    assert task not in _listed(client)
