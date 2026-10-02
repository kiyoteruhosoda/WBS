"""プロジェクトコード（task #187）: 任意。前後の空白を落とし、空は None、32 字まで。"""

from __future__ import annotations

import pytest

from src.domain.entities.project import CODE_MAX_LENGTH, project_code
from src.domain.exceptions import ValidationError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("\tPRJ-01 \n", "PRJ-01"),
        ("A B", "A B"),
        ("あ" * CODE_MAX_LENGTH, "あ" * CODE_MAX_LENGTH),
        (" " + "x" * CODE_MAX_LENGTH + " ", "x" * CODE_MAX_LENGTH),
    ],
)
def test_project_code_is_normalized(raw: str | None, expected: str | None) -> None:
    assert project_code(raw) == expected


def test_project_code_longer_than_the_limit_is_refused() -> None:
    assert CODE_MAX_LENGTH == 32
    with pytest.raises(ValidationError):
        project_code("x" * (CODE_MAX_LENGTH + 1))
