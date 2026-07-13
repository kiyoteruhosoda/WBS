import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.domain.services import overdue_days, priority_score, progress_percent, today_bucket
from src.presentation.api.dependencies import get_db

router = APIRouter(tags=["wbs"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return dict(r)


def _today(conn: sqlite3.Connection, user_id: int = 1) -> date:
    timezone = conn.execute("SELECT timezone FROM users WHERE id=?", (user_id,)).fetchone()
    timezone_name = timezone["timezone"] if timezone else "UTC"
    try:
        return datetime.now(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        return datetime.now(UTC).date()


class CategoryIn(BaseModel):
    name: str
    color: str | None = None
    sort_order: int = 0


class MilestoneIn(BaseModel):
    name: str
    due_date: date | None = None
    description: str | None = None


class TaskIn(BaseModel):
    title: str
    category_id: int | None = None
    priority: int = Field(3, ge=1, le=5)
    urgency: int = Field(3, ge=1, le=5)
    status: str = "TODO"
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: float | None = Field(None, ge=0)
    remaining_hours: float | None = Field(None, ge=0)
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None


class WorkLogIn(BaseModel):
    task_id: int
    work_date: date
    hours: float = Field(..., gt=0, le=24)
    memo: str | None = None


class DependencyIn(BaseModel):
    predecessor_task_id: int
    successor_task_id: int
    dependency_type: str = "FS"
    lag_days: int = 0


class InboxIn(BaseModel):
    title: str
    memo: str | None = None


def _insert(conn: sqlite3.Connection, table: str, data: dict[str, Any]) -> dict[str, Any]:
    keys = [k for k, v in data.items() if v is not None]
    cur = conn.execute(
        f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
        [data[k] for k in keys],
    )
    conn.commit()
    return _row(conn.execute(f"SELECT * FROM {table} WHERE id=?", (cur.lastrowid,)).fetchone())


def _list(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        _row(r)
        for r in conn.execute(f"SELECT * FROM {table} WHERE deleted_at IS NULL ORDER BY id DESC")
    ]


def _patch(conn: sqlite3.Connection, table: str, id: int, data: dict[str, Any]) -> dict[str, Any]:
    if not conn.execute(
        f"SELECT 1 FROM {table} WHERE id=? AND deleted_at IS NULL", (id,)
    ).fetchone():
        raise HTTPException(404, "not found")
    if data:
        data["updated_at"] = _now()
        conn.execute(
            f"UPDATE {table} SET {','.join(f'{k}=?' for k in data)} WHERE id=?",
            [*data.values(), id],
        )
        conn.commit()
    return _row(conn.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone())


def _delete(conn: sqlite3.Connection, table: str, id: int) -> dict[str, str]:
    conn.execute(f"UPDATE {table} SET deleted_at=?, updated_at=? WHERE id=?", (_now(), _now(), id))
    conn.commit()
    return {"status": "deleted"}


@router.get("/categories")
def categories(conn: Db):
    return _list(conn, "categories")


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, conn: Db):
    return _insert(conn, "categories", body.model_dump() | {"user_id": 1})


@router.put("/categories/{id}")
def update_category(id: int, body: CategoryIn, conn: Db):
    return _patch(conn, "categories", id, body.model_dump())


@router.delete("/categories/{id}")
def delete_category(id: int, conn: Db):
    return _delete(conn, "categories", id)


@router.get("/milestones")
def milestones(conn: Db):
    return _list(conn, "milestones")


@router.post("/milestones", status_code=201)
def create_milestone(body: MilestoneIn, conn: Db):
    return _insert(conn, "milestones", body.model_dump(mode="json") | {"user_id": 1})


@router.put("/milestones/{id}")
def update_milestone(id: int, body: MilestoneIn, conn: Db):
    return _patch(conn, "milestones", id, body.model_dump(mode="json", exclude_unset=True))


@router.delete("/milestones/{id}")
def delete_milestone(id: int, conn: Db):
    return _delete(conn, "milestones", id)


@router.get("/tasks")
def tasks(conn: Db, status_: str | None = Query(None, alias="status")):
    sql = (
        "SELECT * FROM tasks WHERE deleted_at IS NULL"
        + (" AND status=?" if status_ else "")
        + " ORDER BY updated_at DESC,id DESC"
    )
    return [
        _summary(conn, r) for r in conn.execute(sql, ((status_,) if status_ else ())).fetchall()
    ]


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, conn: Db):
    return _summary(conn, _insert(conn, "tasks", body.model_dump(mode="json") | {"user_id": 1}))


@router.put("/tasks/{id}")
def update_task(id: int, body: TaskIn, conn: Db):
    data = body.model_dump(mode="json", exclude_unset=True)
    old = conn.execute("SELECT status FROM tasks WHERE id=?", (id,)).fetchone()
    if data.get("status") == "DONE" and old and old["status"] != "DONE":
        data |= {"completed_at": _now(), "remaining_hours": 0}
    elif "status" in data and old and old["status"] == "DONE" and data["status"] != "DONE":
        data["completed_at"] = None
    return _summary(conn, _patch(conn, "tasks", id, data))


@router.delete("/tasks/{id}")
def delete_task(id: int, conn: Db):
    return _delete(conn, "tasks", id)


@router.post("/work-logs", status_code=201)
def create_work_log(body: WorkLogIn, conn: Db):
    return _insert(conn, "work_logs", body.model_dump(mode="json") | {"user_id": 1})


@router.get("/work-logs")
def work_logs(conn: Db):
    return _list(conn, "work_logs")


@router.post("/dependencies", status_code=201)
def create_dependency(body: DependencyIn, conn: Db):
    if _creates_cycle(conn, body.predecessor_task_id, body.successor_task_id):
        raise HTTPException(409, "dependency cycle detected")
    conn.execute(
        "INSERT INTO task_dependencies VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
        tuple(body.model_dump().values()),
    )
    conn.commit()
    return body.model_dump()


@router.get("/dependencies")
def dependencies(conn: Db):
    return [_row(r) for r in conn.execute("SELECT * FROM task_dependencies")]


@router.post("/inbox", status_code=201)
def create_inbox(body: InboxIn, conn: Db):
    return _insert(conn, "inbox_items", body.model_dump() | {"user_id": 1})


@router.get("/inbox")
def inbox(conn: Db):
    return _list(conn, "inbox_items")


@router.post("/inbox/{id}/convert", status_code=201)
def convert_inbox(id: int, conn: Db):
    item = conn.execute(
        "SELECT * FROM inbox_items WHERE id=? AND deleted_at IS NULL", (id,)
    ).fetchone()
    if not item:
        raise HTTPException(404, "not found")
    task = _insert(conn, "tasks", {"user_id": 1, "title": item["title"], "memo": item["memo"]})
    conn.execute(
        "UPDATE inbox_items SET converted_task_id=?, converted_at=? WHERE id=?",
        (task["id"], _now(), id),
    )
    conn.commit()
    return task


@router.get("/today-tasks")
def today_tasks(conn: Db):
    today = _today(conn)
    rows = []
    for r in conn.execute(
        "SELECT * FROM tasks WHERE deleted_at IS NULL AND status NOT IN ('DONE','CANCELLED')"
    ):
        b = today_bucket(r["status"], r["start_date"], r["due_date"], today)
        if b:
            rows.append(_summary(conn, r, today) | {"bucket": b})
    return sorted(rows, key=lambda x: x["score"], reverse=True)


@router.get("/dashboard")
def dashboard(conn: Db):
    today = _today(conn)
    week_ago = (today - timedelta(days=6)).isoformat()
    total = conn.execute("SELECT COUNT(*) c FROM tasks WHERE deleted_at IS NULL").fetchone()["c"]
    open_ = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE deleted_at IS NULL AND status NOT IN ('DONE','CANCELLED')"
    ).fetchone()["c"]
    overdue = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE deleted_at IS NULL AND status NOT IN ('DONE','CANCELLED') AND due_date < ?",
        (today.isoformat(),),
    ).fetchone()["c"]
    hours = conn.execute(
        "SELECT COALESCE(SUM(hours),0) h FROM work_logs WHERE deleted_at IS NULL AND work_date >= ?",
        (week_ago,),
    ).fetchone()["h"]
    return {
        "kpi": {
            "total_tasks": total,
            "open_tasks": open_,
            "overdue_tasks": overdue,
            "weekly_hours": hours,
        },
        "today_tasks": today_tasks(conn),
    }


@router.get("/gantt")
def gantt(conn: Db):
    return {"tasks": tasks(conn), "dependencies": dependencies(conn)}


@router.get("/weekly-review")
def weekly_review(conn: Db):
    return dashboard(conn)["kpi"]


def _summary(
    conn: sqlite3.Connection, r: sqlite3.Row | dict[str, Any], today: date | None = None
) -> dict[str, Any]:
    d = dict(r)
    actual = conn.execute(
        "SELECT COALESCE(SUM(hours),0) h FROM work_logs WHERE task_id=? AND deleted_at IS NULL",
        (d["id"],),
    ).fetchone()["h"]
    od = overdue_days(d.get("due_date"), d["status"], today or _today(conn, d.get("user_id", 1)))
    return d | {
        "actual_hours": actual,
        "progress_percent": progress_percent(d["status"], actual, d.get("remaining_hours")),
        "overdue_days": od,
        "score": priority_score(d["priority"], d["urgency"], od),
    }


def _creates_cycle(conn: sqlite3.Connection, pred: int, succ: int) -> bool:
    if pred == succ:
        return True
    graph: dict[int, list[int]] = {}
    for r in conn.execute("SELECT predecessor_task_id, successor_task_id FROM task_dependencies"):
        graph.setdefault(r["predecessor_task_id"], []).append(r["successor_task_id"])
    graph.setdefault(pred, []).append(succ)
    seen = set()

    def dfs(n: int) -> bool:
        if n == pred:
            return True
        if n in seen:
            return False
        seen.add(n)
        return any(dfs(x) for x in graph.get(n, []))

    return dfs(succ)
