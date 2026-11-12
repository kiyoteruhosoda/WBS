"""Check the periodic reconciliation's decisions without the IdP or a DB.

⚠ **What this guards is the "do not over-suspend" side.** Missed suspensions are caught in two stages
together with the receiver (suspension notices), but over-suspension (dropping everyone just because the IdP is unwell) is not.
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
    """A store that only holds "how many sessions that person has"."""

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
    """⚠ **Do not remove the link of someone who is merely suspended** (if restored at the IdP they get straight back in)."""
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
    """⚠ **Do not suspend people over unknown values.** The day the IdP adds a fourth state, everyone would be suspended."""
    use_case, links, sessions, _ = build({"taro": state}, ["taro"])
    outcome = use_case.execute()

    assert sessions.ended == []
    assert links.unlinked == []
    assert outcome.revoked == 0


def test_someone_missing_from_the_roster_is_left_alone() -> None:
    """A ``sub`` not on the roster is not "gone" (there is simply no answer)."""
    use_case, links, sessions, _ = build({}, ["taro"])
    outcome = use_case.execute()

    assert sessions.ended == []
    assert links.unlinked == []
    assert outcome.checked == 1


def test_everyone_unknown_holds_the_whole_round_back() -> None:
    """⚠ **A tenant mix-up also takes this shape.** Stop before removing everyone."""
    use_case, links, sessions, _ = build(
        {"taro": "unknown", "hanako": "unknown"}, ["taro", "hanako"]
    )
    outcome = use_case.execute()

    assert outcome.held_back is True
    assert sessions.ended == []
    assert links.unlinked == []


def test_one_person_who_is_gone_is_still_handled() -> None:
    """With only one link, "that one person is gone" cannot be told apart, so proceed as usual."""
    use_case, links, sessions, _ = build({"taro": "unknown"}, ["taro"])
    outcome = use_case.execute()

    assert outcome.held_back is False
    assert links.unlinked == [1]


def test_a_roster_we_cannot_read_stops_the_round() -> None:
    """⚠ **Do not confuse "could not fetch" with "everyone left".** Stop with an exception and change nothing."""
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
    """⚠ Do not count someone who stays suspended as one per hour (the record would lose its meaning)."""
    use_case, _, sessions, _ = build({"taro": "blocked"}, ["taro"], counts={})
    outcome = use_case.execute()

    assert sessions.ended == ["taro"]  # still goes to end them (does not know how many there are)
    assert outcome.revoked == 0
