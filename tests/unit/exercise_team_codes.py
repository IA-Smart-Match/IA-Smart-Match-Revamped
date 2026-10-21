"""A fake ``ExerciseTeamCodeRepository`` for router tests (issue #413).

Not a test module (no ``test_`` prefix). Team ``n``'s code is ``fake_code(n)``.
"""

from __future__ import annotations


def fake_code(team_number: int) -> str:
    """Team ``n``'s code in the fake: ``"0n0n"``, so a leading zero is exercised."""
    return f"0{team_number}0{team_number}"


class FakeTeamCodes:
    """Six codes in memory; ``rotate`` records the team and changes its code."""

    def __init__(self) -> None:
        self.codes = {team: fake_code(team) for team in range(1, 7)}
        self.rotated: list[int] = []

    def code_for(self, _session: object, *, team_number: int) -> str | None:
        return self.codes.get(team_number)

    def all_codes(self, _session: object) -> dict[int, str]:
        return dict(self.codes)

    def rotate(self, _session: object, *, team_number: int) -> None:
        self.rotated.append(team_number)
        self.codes[team_number] = "9999" if self.codes[team_number] != "9999" else "8888"
