"""ダッシュボードの時刻も Z で出る（HANDOVER §14）。

`/api/dashboard/today` は素の dict を返していたため、同じタスクでも
`/api/tasks` は `Z` 付き、ダッシュボードは `Z` 無しになっていた。JST の閲覧者には
ダッシュボードだけ 9 時間ずれて見えるので、応答モデルを通すことをここで固定する。
"""

from __future__ import annotations


def test_the_dashboard_renders_the_same_timestamps_as_the_task_list(client) -> None:
    client.post("/api/tasks", json={"title": "きょうの用事", "due_date": "2026-08-26"})

    from_list = client.get("/api/tasks").json()[0]
    buckets = client.get("/api/dashboard/today").json()["buckets"]
    from_dashboard = next(entry for bucket in buckets.values() for entry in bucket)

    assert from_dashboard["created_at"].endswith("Z")
    assert from_dashboard["created_at"] == from_list["created_at"]
    # 応答モデルを通しても、画面が使う派生値は落ちない
    assert from_dashboard["priority_score"] == from_list["priority_score"]
    assert from_dashboard["progress_percent"] == from_list["progress_percent"]
