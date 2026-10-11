import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GameParticipant, GameRoom, User

ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class RoomError(ValueError):
    """Expected room/user state error safe to show to a player."""


async def register_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    display_name: str,
) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            display_name=display_name[:128] or "O‘yinchi",
        )
        session.add(user)
    else:
        user.username = username
        user.display_name = display_name[:128] or "O‘yinchi"
    await session.flush()
    return user


async def _user_has_active_room(session: AsyncSession, user_id: int) -> bool:
    statement = (
        select(GameParticipant.id)
        .join(GameRoom, GameRoom.id == GameParticipant.room_id)
        .where(
            GameParticipant.user_id == user_id,
            GameRoom.status.in_(("lobby", "active")),
        )
        .limit(1)
    )
    return (await session.scalar(statement)) is not None


async def create_room(
    session: AsyncSession,
    owner_id: int,
    *,
    is_public: bool = True,
    min_players: int = 5,
    max_players: int = 15,
) -> GameRoom:
    if min_players < 4 or max_players < min_players or max_players > 50:
        raise RoomError("O‘yinchilar soni sozlamalari noto‘g‘ri.")
    if await session.get(User, owner_id) is None:
        raise RoomError("Avval /start buyrug‘i orqali ro‘yxatdan o‘ting.")
    if await _user_has_active_room(session, owner_id):
        raise RoomError("Siz allaqachon faol xona yoki o‘yindasiz.")

    for _ in range(8):
        code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(6))
        exists = await session.scalar(select(GameRoom.id).where(GameRoom.room_code == code))
        if exists is None:
            room = GameRoom(
                room_code=code,
                owner_id=owner_id,
                is_public=is_public,
                status="lobby",
                min_players=min_players,
                max_players=max_players,
                last_activity_at=datetime.now(timezone.utc),
            )
            session.add(room)
            await session.flush()
            session.add(GameParticipant(room_id=room.id, user_id=owner_id, is_alive=True))
            await session.flush()
            return room

    raise RoomError("Hozir xona kodi yaratib bo‘lmadi. Qayta urinib ko‘ring.")


async def join_room(session: AsyncSession, user_id: int, code: str) -> GameRoom:
    normalized_code = code.strip().upper()
    room = await session.scalar(
        select(GameRoom).where(GameRoom.room_code == normalized_code).with_for_update()
    )
    if room is None or (not room.is_public and room.owner_id != user_id):
        raise RoomError("Bunday xona topilmadi yoki u yopiq.")
    if room.status != "lobby":
        raise RoomError("Bu xona yangi o‘yinchilarni qabul qilmayapti.")
    if await session.get(User, user_id) is None:
        raise RoomError("Avval /start buyrug‘i orqali ro‘yxatdan o‘ting.")

    existing = await session.scalar(
        select(GameParticipant.id).where(
            GameParticipant.room_id == room.id,
            GameParticipant.user_id == user_id,
        )
    )
    if existing is not None:
        return room
    if await _user_has_active_room(session, user_id):
        raise RoomError("Boshqa faol xona yoki o‘yinda bo‘lganingiz uchun qo‘shila olmaysiz.")

    participant_count = await session.scalar(
        select(func.count(GameParticipant.id)).where(GameParticipant.room_id == room.id)
    )
    if (participant_count or 0) >= room.max_players:
        raise RoomError("Xona to‘lib bo‘lgan.")

    session.add(GameParticipant(room_id=room.id, user_id=user_id, is_alive=True))
    room.last_activity_at = datetime.now(timezone.utc)
    await session.flush()
    return room


async def get_room_snapshot(session: AsyncSession, room_id: int) -> tuple[GameRoom, list[User]]:
    room = await session.get(GameRoom, room_id)
    if room is None:
        raise RoomError("Xona topilmadi.")
    users = list(
        (
            await session.scalars(
                select(User)
                .join(GameParticipant, GameParticipant.user_id == User.telegram_id)
                .where(GameParticipant.room_id == room_id)
                .order_by(GameParticipant.joined_at)
            )
        ).all()
    )
    return room, users


async def list_public_rooms(session: AsyncSession, limit: int = 10) -> list[tuple[GameRoom, int]]:
    rooms = list(
        (
            await session.scalars(
                select(GameRoom)
                .where(GameRoom.is_public.is_(True), GameRoom.status == "lobby")
                .order_by(GameRoom.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    result: list[tuple[GameRoom, int]] = []
    for room in rooms:
        count = await session.scalar(
            select(func.count(GameParticipant.id)).where(GameParticipant.room_id == room.id)
        )
        result.append((room, count or 0))
    return result


async def leave_room(session: AsyncSession, user_id: int, room_id: int | None = None) -> str:
    statement = (
        select(GameParticipant, GameRoom)
        .join(GameRoom, GameRoom.id == GameParticipant.room_id)
        .where(GameParticipant.user_id == user_id, GameRoom.status == "lobby")
    )
    if room_id is not None:
        statement = statement.where(GameRoom.id == room_id)
    statement = statement.order_by(GameParticipant.joined_at).limit(1).with_for_update()
    result = (await session.execute(statement)).first()
    if result is None:
        raise RoomError("Siz chiqishingiz mumkin bo‘lgan kutish xonasida emassiz.")

    participant, room = result
    session.delete(participant)
    remaining = list(
        (
            await session.scalars(
                select(GameParticipant)
                .where(GameParticipant.room_id == room.id)
                .order_by(GameParticipant.joined_at)
            )
        ).all()
    )
    if room.owner_id == user_id:
        if remaining:
            room.owner_id = remaining[0].user_id
        else:
            room.status = "cancelled"
    if not remaining and room.owner_id != user_id:
        room.status = "cancelled"
    room.last_activity_at = datetime.now(timezone.utc)
    await session.flush()
    return room.room_code
