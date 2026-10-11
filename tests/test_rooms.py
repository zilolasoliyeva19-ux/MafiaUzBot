import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, GameParticipant, GameRoom
from app.services.rooms import RoomError, create_room, get_room_snapshot, join_room, leave_room, register_user


@pytest.mark.asyncio
async def test_room_creation_joining_duplicate_protection_and_owner_transfer() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with factory() as session, session.begin():
            await register_user(session, 101, "owner", "Xona egasi")
            await register_user(session, 202, "guest", "Mehmon")

        async with factory() as session, session.begin():
            room = await create_room(session, 101, min_players=4, max_players=5)
            room_id = room.id
            room_code = room.room_code

        async with factory() as session, session.begin():
            joined = await join_room(session, 202, room_code)
            assert joined.id == room_id
            # Joining the same room twice must not create a duplicate participant.
            await join_room(session, 202, room_code)

        async with factory() as session:
            room, players = await get_room_snapshot(session, room_id)
            assert len(players) == 2
            assert {player.telegram_id for player in players} == {101, 202}
            assert room.owner_id == 101

        async with factory() as session, session.begin():
            code = await leave_room(session, 101, room_id)
            assert code == room_code

        async with factory() as session:
            room = await session.get(GameRoom, room_id)
            participants = list(
                (await session.scalars(
                    select(GameParticipant).where(GameParticipant.room_id == room_id)
                )).all()
            )
            assert room is not None
            assert room.owner_id == 202
            assert len(participants) == 1
            assert participants[0].user_id == 202
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_cannot_join_multiple_active_lobbies() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with factory() as session, session.begin():
            await register_user(session, 301, None, "Birinchi")
            await register_user(session, 302, None, "Ikkinchi")
            await register_user(session, 303, None, "Uchinchi")
            room = await create_room(session, 301, min_players=4, max_players=5)
            code = room.room_code

        async with factory() as session, session.begin():
            await join_room(session, 302, code)

        async with factory() as session, session.begin():
            with pytest.raises(RoomError, match="faol xona"):
                await create_room(session, 302, min_players=4, max_players=5)
    finally:
        await engine.dispose()
