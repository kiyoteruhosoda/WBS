import pytest

from src.domain.value_objects.redirect_target import DEFAULT_REDIRECT_PATH, RedirectTarget


@pytest.mark.parametrize(
    "raw",
    [
        "https://evil.example/steal",
        "//evil.example/steal",
        "/\\evil.example",
        "http://evil.example",
        "tasks",                       # a relative path leaves the return base ambiguous
        "/tasks\\@evil.example",       # some browsers read `\` as `/`
        "/tasks\nLocation: https://evil.example",
        "",
        None,
    ],
)
def test_external_or_ambiguous_targets_fall_back_to_root(raw) -> None:
    assert RedirectTarget.parse(raw).path == DEFAULT_REDIRECT_PATH


@pytest.mark.parametrize("raw", ["/", "/tasks", "/tasks/12?edit=1", "/gantt#today"])
def test_internal_paths_are_kept(raw) -> None:
    assert RedirectTarget.parse(raw).path == raw


def test_surrounding_whitespace_is_trimmed() -> None:
    assert RedirectTarget.parse("  /inbox  ").path == "/inbox"
