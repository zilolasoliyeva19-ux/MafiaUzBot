"""Create the initial MafiaUzBot database schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("games_played", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("is_banned", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_users_wins", "users", ["wins"])

    op.create_table(
        "game_rooms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_code", sa.String(length=8), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("min_players", sa.Integer(), nullable=False),
        sa.Column("max_players", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("min_players >= 4", name="ck_room_min_players"),
        sa.CheckConstraint("max_players >= min_players", name="ck_room_player_range"),
        sa.UniqueConstraint("room_code"),
    )
    op.create_index("ix_game_rooms_room_code", "game_rooms", ["room_code"])
    op.create_index("ix_game_rooms_status_activity", "game_rooms", ["status", "last_activity_at"])

    op.create_table(
        "game_participants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("game_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("is_alive", sa.Boolean(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("room_id", "user_id", name="uq_participant_room_user"),
    )
    op.create_index("ix_participants_user", "game_participants", ["user_id"])

    op.create_table(
        "game_matches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("game_rooms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("phase", sa.String(length=24), nullable=False),
        sa.Column("winner_team", sa.String(length=24), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_matches_status_started", "game_matches", ["status", "started_at"])

    op.create_table(
        "votes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("game_matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voter_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("match_id", "voter_id", "round_number", name="uq_vote_per_round"),
    )
    op.create_index("ix_votes_match_round", "votes", ["match_id", "round_number"])

    op.create_table(
        "night_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("game_matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("match_id", "actor_id", "round_number", name="uq_night_action_actor_round"),
    )
    op.create_index("ix_night_actions_match_round", "night_actions", ["match_id", "round_number"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_created_at", "admin_audit_logs", ["created_at"])

    op.create_table(
        "bot_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bot_settings")
    op.drop_index("ix_audit_created_at", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_night_actions_match_round", table_name="night_actions")
    op.drop_table("night_actions")
    op.drop_index("ix_votes_match_round", table_name="votes")
    op.drop_table("votes")
    op.drop_index("ix_matches_status_started", table_name="game_matches")
    op.drop_table("game_matches")
    op.drop_index("ix_participants_user", table_name="game_participants")
    op.drop_table("game_participants")
    op.drop_index("ix_game_rooms_status_activity", table_name="game_rooms")
    op.drop_index("ix_game_rooms_room_code", table_name="game_rooms")
    op.drop_table("game_rooms")
    op.drop_index("ix_users_wins", table_name="users")
    op.drop_table("users")
