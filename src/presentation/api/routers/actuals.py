"""Actuals visualization: plan vs. actual (task #162 / ADR-0017; schedules and time punches were removed in task #543 / ADR-0070).

- ``GET /actuals/tasks``: per-task estimate, actual and remaining, and why the remaining time should be reviewed
    (``review_only=true`` returns only those needing review; opened after Tracker's closing arrives)
- ``GET /actuals/gantt``: actual bars for the Gantt chart (first to last day of confirmed actuals, and per-day actuals)
- ``GET /actuals/periods``: confirmed actuals per period (half month, week, month)
- ``GET /actuals/breakdown``: stacked totals by category, milestone and project (per branch)
- ``GET /actuals/export.csv``: period x day x task x hours (for pasting into external effort systems)

All dates are in the user's time zone (setting). Without a range, the 6 periods ending with the current one.
Each can be narrowed with ``project_id`` to tasks of that project and its descendants (ADR-0024).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.application.dto.actuals_dto import BreakdownGroupBy, ExportRow
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
    dt.date | None, Query(alias="from", description="First day of the range (user's date, inclusive)")
]
ToDate = Annotated[
    dt.date | None, Query(alias="to", description="Last day of the range (user's date, inclusive)")
]
ProjectScope = Annotated[
    int | None,
    Query(description="Only tasks in this project and its descendant projects"),
]
Unclassified = Annotated[
    bool, Query(description="If true, only tasks without a project (uncategorized)")
]
Unit = Annotated[
    ReportPeriodUnit,
    Query(description="Period unit: closing (half month: days 1-15 and 16-end) / week (starts Monday) / month"),
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
            from_date,
            to_date,
            project_id,
            unclassified,
        )
    )


@router.get(
    "/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV in UTF-8 (with BOM)"}},
)
def export_actuals(
    uc: ActualsUseCasesDep,
    current_user: CurrentUserDep,
    from_date: Annotated[dt.date, Query(alias="from", description="First day (user's date, inclusive)")],
    to_date: Annotated[dt.date, Query(alias="to", description="Last day (user's date, inclusive)")],
    project_id: ProjectScope = None,
    unclassified: Unclassified = False,
) -> Response:
    """Period (half month) x day x task x hours (confirmed actuals). A BOM is added so spreadsheets do not garble it."""
    rows = uc.export(current_user.user_id, from_date, to_date, project_id, unclassified)
    filename = f"actuals-{from_date.isoformat()}-{to_date.isoformat()}.csv"
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
                row.task_id,
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
