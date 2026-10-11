from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_wins", "wins"),)

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(128), default="O‘yinchi")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)


class GameRoom(Base):
    __tablename__ = "game_rooms"
    __table_args__ = (
        CheckConstraint("min_players >= 4", name="ck_room_min_players"),
        CheckConstraint("max_players >= min_players", name="ck_room_player_range"),
        Index("ix_game_rooms_status_activity", "status", "last_activity_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(String(8), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="RESTRICT"))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(24), default="lobby")
    min_players: Mapped[int] = mapped_column(Integer, default=5)
    max_players: Mapped[int] = mapped_column(Integer, default=15)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GameParticipant(Base):
    __tablename__ = "game_participants"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_participant_room_user"),
        Index("ix_participants_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("game_rooms.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    role: Mapped[str | None] = mapped_column(String(32))
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GameMatch(Base):
    __tablename__ = "game_matches"
    __table_args__ = (Index("ix_matches_status_started", "status", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("game_rooms.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="active")
    phase: Mapped[str] = mapped_column(String(24), default="role_assignment")
    winner_team: Mapped[str | None] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("match_id", "voter_id", "round_number", name="uq_vote_per_round"),
        Index("ix_votes_match_round", "match_id", "round_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("game_matches.id", ondelete="CASCADE"))
    voter_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    round_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NightAction(Base):
    __tablename__ = "night_actions"
    __table_args__ = (
        UniqueConstraint("match_id", "actor_id", "round_number", name="uq_night_action_actor_round"),
        Index("ix_night_actions_match_round", "match_id", "round_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("game_matches.id", ondelete="CASCADE"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String(32))
    round_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (Index("ix_audit_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
