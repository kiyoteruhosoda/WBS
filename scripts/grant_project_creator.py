"""いちばん上のプロジェクトを作れる人の印を付け外しする（task #734 / ADR-0065）。

    python scripts/grant_project_creator.py <メール>            # 付ける
    python scripts/grant_project_creator.py <メール> --revoke   # 外す

相手は WBS に 1 度ログインしたことのある人（``users`` の行）。外しても、もう作った根の管理者のままで、
メンバーになっている木の中では今までどおり下のプロジェクトを作れる。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# スクリプト直接実行でも `src` パッケージを解決できるよう、リポジトリルートを import パスへ加える。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.use_cases.project_creator_use_cases import ProjectCreatorUseCases  # noqa: E402
from src.domain.exceptions import NotFoundError  # noqa: E402
from src.infrastructure.database.session import get_db_session, init_engine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="いちばん上のプロジェクトを作れる人の印を付け外しする")
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="印を外す")
    args = parser.parse_args(argv)

    init_engine()
    with get_db_session() as session:
        try:
            user = ProjectCreatorUseCases(session).allow(args.email, allowed=not args.revoke)
        except NotFoundError:
            print(f"{args.email} は WBS にログインしたことがありません", file=sys.stderr)
            return 1
    print(f"{user.email}: can_create_projects={user.can_create_projects}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
