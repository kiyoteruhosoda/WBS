"""実績の見える化: 予定 vs 実績・計画 vs 実績（task #162 / ADR-0017）。

- ``GET /actuals/tasks``: タスクごとの見積・予定済み・実績・残と、残を見直してほしい理由
  （``review_only=true`` で見直しが要るものだけ。締めの直後に開く）
- ``GET /actuals/gantt``: ガントの実績の帯（確定した実績の最初〜最後の日と、日ごとの実績）
- ``GET /actuals/periods``: 期間ごと（締めの期間・週・月）の予定と打刻の差・タスク外の割合・確定実績
- ``GET /actuals/breakdown``: カテゴリ別・マイルストーン別・プロジェクト別（枝ごと）の積み上げ
- ``GET /actuals/export.csv``: 期間 × 日 × タスク × 時間（外の工数の仕組みへ貼る用）

日付はすべて利用者のタイムゾーン（設定）。範囲を省くと今の期間で終わる 6 期間。
どれも ``project_id`` で、そのプロジェクトと子孫のタスクの分だけに絞れる（ADR-0024）。
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.application.dto.actuals_dto import BreakdownGroupBy, ExportRow, TimeSource
from src.domain.value_objects.report_period import ReportPeriodUnit
from src.presentation.api.dependencies import ActualsUseCasesDep, CurrentUserDep
from src.presentation.api.schemas.actuals_schemas import (
    BreakdownResponse,
    GanttActualSpanResponse,
    PeriodReportResponse,
    TaskActualsResponse,
)

router = APIRouter(prefix="/actuals", tags=["actuals"])

FromDate = Annotated[
    dt.date | None, Query(alias="from", description="範囲の初日（利用者の日付、含む）")
]
ToDate = Annotated[
    dt.date | None, Query(alias="to", description="範囲の末日（利用者の日付、含む）")
]
ProjectScope = Annotated[
    int | None,
    Query(description="このプロジェクトと、その子孫のプロジェクトのタスクの分だけ（タスク外は数えない）"),
]
Unclassified = Annotated[
    bool, Query(description="true ならプロジェクトの無い（未分類の）タスクの分だけ（タスク外は数えない）")
]
Unit = Annotated[
    ReportPeriodUnit,
    Query(description="期間の単位: closing（締めの期間）/ week（月曜始まり）/ month"),
]

CSV_HEADER = [
    "period_start",
    "period_end",
    "date",
    "task_id",
    "task",
    "category",
    "milestone",
    "hours",
    "seconds",
]


@router.get("/tasks", response_model=TaskActualsResponse)
def get_task_actuals(
    uc: ActualsUseCasesDep,
    current_user: CurrentUserDep,
    review_only: bool = False,
    project_id: ProjectScope = None,
    unclassified: Unclassified = False,
) -> TaskActualsResponse:
    return TaskActualsResponse.from_board(
        uc.task_board(
            current_user.user_id,
            review_only=review_only,
            project_id=project_id,
            unclassified=unclassified,
        )
    )


@router.get("/gantt", response_model=list[GanttActualSpanResponse])
def get_gantt_actuals(
    uc: ActualsUseCasesDep,
    current_user: CurrentUserDep,
    from_date: FromDate = None,
    to_date: ToDate = None,
    project_id: ProjectScope = None,
    unclassified: Unclassified = False,
) -> list[GanttActualSpanResponse]:
    return [
        GanttActualSpanResponse.from_span(s)
        for s in uc.gantt(current_user.user_id, from_date, to_date, project_id, unclassified)
    ]


@router.get("/periods", response_model=PeriodReportResponse)
def get_period_report(
    uc: ActualsUseCasesDep,
    current_user: CurrentUserDep,
    unit: Unit = ReportPeriodUnit.CLOSING,
    from_date: FromDate = None,
    to_date: ToDate = None,
    project_id: ProjectScope = None,
    unclassified: Unclassified = False,
) -> PeriodReportResponse:
    return PeriodReportResponse.from_report(
        uc.periods(current_user.user_id, unit, from_date, to_date, project_id, unclassified)
    )


@router.get("/breakdown", response_model=BreakdownResponse)
def get_breakdown(
    uc: ActualsUseCasesDep,
    current_user: CurrentUserDep,
    unit: Unit = ReportPeriodUnit.CLOSING,
    group_by: BreakdownGroupBy = BreakdownGroupBy.CATEGORY,
    source: TimeSource = TimeSource.CONFIRMED,
    from_date: FromDate = None,
    to_date: ToDate = None,
    project_id: ProjectScope = None,
    unclassified: Unclassified = False,
) -> BreakdownResponse:
    return BreakdownResponse.from_breakdown(
        uc.breakdown(
            current_user.user_id,
            unit,
            group_by,
            source,
            from_date,
            to_date,
            project_id,
            unclassified,
        )
    )


@router.get(
    "/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "UTF-8（BOM 付き）の CSV"}},
)
def export_actuals(
    uc: ActualsUseCasesDep,
    current_user: CurrentUserDep,
    from_date: Annotated[dt.date, Query(alias="from", description="初日（利用者の日付、含む）")],
    to_date: Annotated[dt.date, Query(alias="to", description="末日（利用者の日付、含む）")],
    source: TimeSource = TimeSource.CONFIRMED,
    project_id: ProjectScope = None,
    unclassified: Unclassified = False,
) -> Response:
    """期間（締めの期間）× 日 × タスク × 時間。表計算ソフトで文字化けしないよう BOM を付ける。"""
    rows = uc.export(current_user.user_id, from_date, to_date, source, project_id, unclassified)
    filename = f"actuals-{source.value}-{from_date.isoformat()}-{to_date.isoformat()}.csv"
    return Response(
        content="﻿" + render_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def render_csv(rows: list[ExportRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            [
                row.period.first_day.isoformat(),
                row.period.last_day.isoformat(),
                row.work_date.isoformat(),
                row.task_id if row.task_id is not None else "",
                row.task_title or "",
                row.category_name or "",
                row.milestone_name or "",
                str(
                    (Decimal(row.seconds) / Decimal(3600)).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                ),
                row.seconds,
            ]
        )
    return buffer.getvalue()
