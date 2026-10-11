from app.models import Base, GameParticipant, GameRoom, Vote


def test_expected_core_tables_are_registered() -> None:
    assert {
        "users",
        "game_rooms",
        "game_participants",
        "game_matches",
        "votes",
        "night_actions",
        "admin_audit_logs",
        "bot_settings",
    }.issubset(Base.metadata.tables.keys())


def test_room_code_is_unique() -> None:
    constraints = GameRoom.__table__.constraints
    assert any(
        constraint.__class__.__name__ == "UniqueConstraint"
        and {column.name for column in constraint.columns} == {"room_code"}
        for constraint in constraints
    )


def test_duplicate_participant_and_vote_constraints_exist() -> None:
    participant_constraints = [
        {column.name for column in constraint.columns}
        for constraint in GameParticipant.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert {"room_id", "user_id"} in participant_constraints

    vote_constraints = [
        {column.name for column in constraint.columns}
        for constraint in Vote.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert {"match_id", "voter_id", "round_number"} in vote_constraints
