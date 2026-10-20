"""プロジェクトのメンバーの役割（task #544 / ADR-0055）。"""

from __future__ import annotations

import enum


class ProjectRole(enum.StrEnum):
    MANAGER = "manager"
    """管理者。メンバーの出し入れ・役割の変更、いちばん上のプロジェクトを消す・他の下へ移す。"""
    MEMBER = "member"
    """メンバー。その木のプロジェクト・タスク・マイルストーンを読み書きする。"""
