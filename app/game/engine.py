from collections import Counter
from collections.abc import Iterable, Mapping

from app.game.roles import Role, is_mafia_role


def evaluate_winner(alive_roles: Iterable[Role]) -> str | None:
    """Return 'town', 'mafia', 'draw', or None while the match continues."""
    roles = list(alive_roles)
    if not roles:
        return "draw"
    mafia_count = sum(1 for role in roles if is_mafia_role(role))
    town_count = len(roles) - mafia_count
    if mafia_count == 0:
        return "town"
    if mafia_count >= town_count:
        return "mafia"
    return None


def resolve_plurality(votes: Mapping[int, int], eligible_targets: set[int]) -> int | None:
    """Resolve votes, returning None for no valid votes or a tie."""
    counts = Counter(
        target_id
        for target_id in votes.values()
        if target_id in eligible_targets
    )
    if not counts:
        return None
    highest = max(counts.values())
    winners = [target for target, count in counts.items() if count == highest]
    return winners[0] if len(winners) == 1 else None


def resolve_mafia_target(
    target_votes: Iterable[int],
    living_player_ids: set[int],
    protected_player_id: int | None = None,
) -> int | None:
    """Resolve the Mafia's collective target; protection cancels the elimination."""
    target = resolve_plurality(
        {index: target for index, target in enumerate(target_votes)},
        living_player_ids,
    )
    if target is None or target == protected_player_id:
        return None
    return target
