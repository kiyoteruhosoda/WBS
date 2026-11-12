"""Grant or revoke the flag for people who can create top-level projects (task #734 / ADR-0065).

    python scripts/grant_project_creator.py <email>            # grant
    python scripts/grant_project_creator.py <email> --revoke   # revoke

The target must have signed in to WBS at least once (a row in ``users``). Revoking keeps them admin of roots they already created,
and inside trees they are members of they can still create child projects as before.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add the repository root to the import path so the `src` package resolves even when the script is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.use_cases.project_creator_use_cases import ProjectCreatorUseCases  # noqa: E402
from src.domain.exceptions import NotFoundError  # noqa: E402
from src.infrastructure.database.session import get_db_session, init_engine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grant or revoke the flag for people who can create top-level projects")
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="revoke the flag")
    args = parser.parse_args(argv)

    init_engine()
    with get_db_session() as session:
        try:
            user = ProjectCreatorUseCases(session).allow(args.email, allowed=not args.revoke)
        except NotFoundError:
            print(f"{args.email} has never signed in to WBS", file=sys.stderr)
            return 1
    print(f"{user.email}: can_create_projects={user.can_create_projects}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
