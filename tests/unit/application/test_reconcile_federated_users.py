"""定期照合の判断を、IdP も DB も使わずに確かめる。

⚠ **ここで守っているのは「止めすぎない」ほう。** 止め損ねは受け口（停止の通知）と
二段で拾えるが、止めすぎ——IdP が不調なだけで全員を落とす——は拾えない。
"""

import pytest

from src.application.ports.roster_gateway import RosterGateway
from src.application.use_cases.reconcile_federated_users import ReconcileFederatedUsers
from src.domain.entities.identity_link import IdentityLink
from src.domain.exceptions import IdentityProviderUnavailableError
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.roster import Roster, RosterEntry, RosterState

ISSUER = "https://idp.example.com/realms/wbs"


class FakeRoster(RosterGateway):
    def __init__(self, states: dict[str, str], *, fails: bool = False) -> None:
        self._states = states
        self._fails = fails
        self.asked: list[tuple[str, ...]] = []

    def fetch(self, *, issuer, subjects):
        if self._fails:
            raise IdentityProviderUnavailableError("the idp is down")
        self.asked.append(subjects)
        return Roster(
            entries=tuple(
                RosterEntry(subject=sub, state=RosterState.of(self._states[sub]))
                for sub in subjects
                if sub in self._states
            )
        )


class FakeLinks:
    def __init__(self, subjects: list[str]) -> None:
        self.links = [
            IdentityLink(
                id=index + 1,
                user_id=index + 1,
                identity=FederatedIdentity(issuer=ISSUER, subject=subject),
            )
            for index, subject in enumerate(subjects)
        ]
        self.unlinked: list[int] = []

    def list_for_issuer(self, issuer):
        return [link for link in self.links if link.issuer == issuer]

    def unlink(self, link_id):
        self.unlinked.append(link_id)
        self.links = [link for link in self.links if link.id != link_id]


class FakeSessions:
    """「その人にセッションが何本あるか」だけを持つ置き場。"""

    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self.counts = counts or {}
        self.ended: list[str] = []

    def delete_for_identity(self, identity, *, idp_session_id=None):
        self.ended.append(identity.subject)
        return self.counts.pop(identity.subject, 0)


def build(states, subjects, counts=None, **roster_kwargs):
    links = FakeLinks(subjects)
    sessions = FakeSessions(counts if counts is not None else dict.fromkeys(subjects, 1))
    roster = FakeRoster(states, **roster_kwargs)
    use_case = ReconcileFederatedUsers(
        issuer=ISSUER, links=links, sessions=sessions, roster=roster
    )
    return use_case, links, sessions, roster


def test_a_blocked_person_loses_their_sessions_but_keeps_the_link() -> None:
    """⚠ **止まっただけの人の結び付きは外さない**（IdP で戻ればそのまま入れる）。"""
    use_case, links, sessions, _ = build({"taro": "blocked", "hanako": "allowed"}, ["taro", "hanako"])
    outcome = use_case.execute()

    assert sessions.ended == ["taro"]
    assert links.unlinked == []
    assert (outcome.checked, outcome.revoked, outcome.unlinked) == (2, 1, 0)


def test_a_person_who_is_gone_also_loses_the_link() -> None:
    use_case, links, sessions, _ = build({"taro": "unknown", "hanako": "allowed"}, ["taro", "hanako"])
    outcome = use_case.execute()

    assert sessions.ended == ["taro"]
    assert links.unlinked == [1]
    assert (outcome.revoked, outcome.unlinked) == (1, 1)


def test_an_allowed_person_is_left_alone() -> None:
    use_case, links, sessions, _ = build({"taro": "allowed"}, ["taro"])
    outcome = use_case.execute()

    assert sessions.ended == []
    assert links.unlinked == []
    assert outcome.revoked == 0


@pytest.mark.parametrize("state", ["", "retired", "suspended-maybe"])
def test_a_state_we_do_not_know_changes_nothing(state) -> None:
    """⚠ **知らない値で人を止めない。** IdP が 4 つ目の状態を足した日に全員が止まる。"""
    use_case, links, sessions, _ = build({"taro": state}, ["taro"])
    outcome = use_case.execute()

    assert sessions.ended == []
    assert links.unlinked == []
    assert outcome.revoked == 0


def test_someone_missing_from_the_roster_is_left_alone() -> None:
    """名簿に載っていない ``sub`` は「消えた」ではない（答えが無いだけ）。"""
    use_case, links, sessions, _ = build({}, ["taro"])
    outcome = use_case.execute()

    assert sessions.ended == []
    assert links.unlinked == []
    assert outcome.checked == 1


def test_everyone_unknown_holds_the_whole_round_back() -> None:
    """⚠ **テナントの取り違えでもこの形になる。** 全員分を外す前に止まる。"""
    use_case, links, sessions, _ = build(
        {"taro": "unknown", "hanako": "unknown"}, ["taro", "hanako"]
    )
    outcome = use_case.execute()

    assert outcome.held_back is True
    assert sessions.ended == []
    assert links.unlinked == []


def test_one_person_who_is_gone_is_still_handled() -> None:
    """結び付きが 1 件だけなら「その 1 人が消えた」と区別が付かないので、通常どおり。"""
    use_case, links, sessions, _ = build({"taro": "unknown"}, ["taro"])
    outcome = use_case.execute()

    assert outcome.held_back is False
    assert links.unlinked == [1]


def test_a_roster_we_cannot_read_stops_the_round() -> None:
    """⚠ **引けないことと「全員辞めた」を混ぜない。** 例外で止め、何も変えない。"""
    use_case, links, sessions, _ = build({}, ["taro"], fails=True)
    with pytest.raises(IdentityProviderUnavailableError):
        use_case.execute()

    assert sessions.ended == []
    assert links.unlinked == []


def test_nothing_is_asked_when_no_one_is_linked() -> None:
    use_case, _, _, roster = build({}, [])
    outcome = use_case.execute()

    assert roster.asked == []
    assert outcome.checked == 0


def test_a_person_with_no_sessions_left_is_not_counted_again() -> None:
    """⚠ 止まったままの人を毎時 1 人として数えない（記録が意味を失う）。"""
    use_case, _, sessions, _ = build({"taro": "blocked"}, ["taro"], counts={})
    outcome = use_case.execute()

    assert sessions.ended == ["taro"]  # 消しには行く（何本あるかは知らない）
    assert outcome.revoked == 0
