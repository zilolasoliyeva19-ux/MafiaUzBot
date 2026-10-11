import pytest

from app.game.engine import evaluate_winner, resolve_mafia_target, resolve_plurality
from app.game.roles import Role, RoleAssignmentError, assign_roles, investigation_result


@pytest.mark.parametrize("player_count", [4, 5, 6, 7, 8, 9, 12, 15])
def test_role_assignment_matches_player_count(player_count: int) -> None:
    player_ids = list(range(1000, 1000 + player_count))
    assigned = assign_roles(player_ids)
    assert set(assigned) == set(player_ids)
    assert len(assigned) == player_count
    assert sum(role in {Role.MAFIA, Role.DON} for role in assigned.values()) >= 1
    assert Role.DETECTIVE in assigned.values()


def test_role_assignment_rejects_duplicate_ids_and_small_lobbies() -> None:
    with pytest.raises(RoleAssignmentError):
        assign_roles([1, 2, 3])
    with pytest.raises(RoleAssignmentError):
        assign_roles([1, 2, 2, 3])


def test_don_is_resistant_to_investigation() -> None:
    assert investigation_result(Role.DON) == "not_mafia"
    assert investigation_result(Role.MAFIA) == "mafia"
    assert investigation_result(Role.CITIZEN) == "not_mafia"


def test_winner_conditions() -> None:
    assert evaluate_winner([]) == "draw"
    assert evaluate_winner([Role.CITIZEN, Role.DETECTIVE]) == "town"
    assert evaluate_winner([Role.MAFIA, Role.CITIZEN]) == "mafia"
    assert evaluate_winner([Role.MAFIA, Role.CITIZEN, Role.DOCTOR]) is None


def test_plurality_tie_and_invalid_targets() -> None:
    assert resolve_plurality({1: 3, 2: 4}, {3, 4}) is None
    assert resolve_plurality({1: 99, 2: 3}, {3, 4}) == 3
    assert resolve_plurality({}, {3, 4}) is None


def test_doctor_protection_prevents_night_elimination() -> None:
    assert resolve_mafia_target([2, 2, 3], {1, 2, 3}, protected_player_id=2) is None
    assert resolve_mafia_target([2, 2, 3], {1, 2, 3}, protected_player_id=1) == 2
