from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session_factory
from app.models import GameRoom
from app.services.rooms import (
    RoomError,
    create_room,
    get_room_snapshot,
    join_room,
    leave_room,
    list_public_rooms,
    register_user,
)

router = Router(name="rooms")


def room_keyboard(room_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Yangilash", callback_data=f"room:refresh:{room_id}"),
                InlineKeyboardButton(text="🚪 Xonadan chiqish", callback_data=f"room:leave:{room_id}"),
            ]
        ]
    )


def room_text(room: GameRoom, players: list, count: int | None = None) -> str:
    actual_count = len(players) if count is None else count
    owner = next((player for player in players if player.telegram_id == room.owner_id), None)
    owner_name = escape(owner.display_name if owner else "O‘yinchi")
    player_lines = "\n".join(
        f"• {escape(player.display_name)}" + (" 👑" if player.telegram_id == room.owner_id else "")
        for player in players
    ) or "Hozircha o‘yinchilar yo‘q"
    return (
        f"🏠 <b>Mafia xonasi: {escape(room.room_code)}</b>\n\n"
        f"👑 Xona egasi: {owner_name}\n"
        f"👥 O‘yinchilar: <b>{actual_count}/{room.max_players}</b>\n"
        f"🎯 Boshlash uchun: kamida {room.min_players} kishi\n"
        f"📌 Holat: kutish xonasi\n\n"
        f"<b>Ishtirokchilar:</b>\n{player_lines}\n\n"
        "Xona kodi orqali do‘stlaringizni taklif qiling. O‘yin boshlash mexanikasi keyingi bosqichda ulanadi."
    )


async def _ensure_registered(session: AsyncSession, message: Message) -> int:
    if message.from_user is None:
        raise RoomError("Telegram foydalanuvchisini aniqlab bo‘lmadi.")
    user = message.from_user
    name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
    await register_user(session, user.id, user.username, name or user.full_name)
    return user.id


async def _show_room(message: Message, room_id: int) -> None:
    async with get_session_factory()() as session:
        room, players = await get_room_snapshot(session, room_id)
        count = len(players)
    await message.answer(room_text(room, players, count), reply_markup=room_keyboard(room_id))


@router.message(Command("create"))
@router.message(F.text == "🏠 Xona yaratish")
async def create_room_handler(message: Message) -> None:
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                user_id = await _ensure_registered(session, message)
                settings = get_settings()
                room = await create_room(
                    session,
                    user_id,
                    is_public=True,
                    min_players=settings.min_players,
                    max_players=settings.max_players,
                )
                room_id = room.id
                room_code = room.room_code
        await message.answer(
            f"✅ Xona yaratildi! Kodi: <code>{escape(room_code)}</code>\n"
            "Do‘stlaringizga kodni yuboring yoki quyidagi xabarni ulashing."
        )
        await _show_room(message, room_id)
    except RoomError as exc:
        await message.answer(f"⚠️ {escape(str(exc))}")
    except Exception:
        await message.answer("❌ Xona yaratishda xatolik yuz berdi. Keyinroq qayta urinib ko‘ring.")
        raise


@router.message(Command("join"))
async def join_room_command_handler(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Xonaga qo‘shilish uchun: <code>/join KOD</code>")
        return
    await _join_by_code(message, parts[1])


@router.message(F.text == "🚪 Xonaga qo‘shilish")
async def join_room_help_handler(message: Message) -> None:
    await message.answer("Xona kodini kiriting: <code>/join KOD</code>")


async def _join_by_code(message: Message, code: str) -> None:
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                user_id = await _ensure_registered(session, message)
                room = await join_room(session, user_id, code)
                room_id = room.id
        await _show_room(message, room_id)
    except RoomError as exc:
        await message.answer(f"⚠️ {escape(str(exc))}")
    except Exception:
        await message.answer("❌ Xonaga qo‘shilishda xatolik yuz berdi. Keyinroq urinib ko‘ring.")
        raise


@router.message(Command("play"))
@router.message(F.text == "🎮 O‘yin o‘ynash")
async def list_rooms_handler(message: Message) -> None:
    try:
        async with get_session_factory()() as session:
            rooms = await list_public_rooms(session)
        if not rooms:
            await message.answer(
                "🎮 Hozir ochiq kutish xonalari yo‘q. “🏠 Xona yaratish” tugmasi orqali yangi xona ochishingiz mumkin."
            )
            return
        rows = [
            [InlineKeyboardButton(
                text=f"🚪 {room.room_code} · {count}/{room.max_players}",
                callback_data=f"room:join:{room.room_code}",
            )]
            for room, count in rooms
        ]
        await message.answer(
            "🎮 <b>Ochiq xonalar</b>\nQo‘shilish uchun xonani tanlang:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception:
        await message.answer("❌ Xonalarni yuklab bo‘lmadi. Keyinroq urinib ko‘ring.")
        raise


@router.message(Command("leave"))
async def leave_room_command_handler(message: Message) -> None:
    if message.from_user is None:
        return
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                code = await leave_room(session, message.from_user.id)
        await message.answer(f"🚪 Siz <code>{escape(code)}</code> xonasidan chiqdingiz.")
    except RoomError as exc:
        await message.answer(f"⚠️ {escape(str(exc))}")


@router.callback_query(F.data.startswith("room:join:"))
async def join_room_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Foydalanuvchi aniqlanmadi.", show_alert=True)
        return
    code = (callback.data or "").rsplit(":", 1)[-1]
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                user = callback.from_user
                name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
                await register_user(session, user.id, user.username, name or user.full_name)
                room = await join_room(session, user.id, code)
                room_id = room.id
        await callback.answer("Xonaga qo‘shildingiz!")
        if callback.message and isinstance(callback.message, Message):
            await _show_room(callback.message, room_id)
    except RoomError as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer("Xatolik yuz berdi. Keyinroq urinib ko‘ring.", show_alert=True)
        raise


@router.callback_query(F.data.startswith("room:refresh:"))
async def refresh_room_callback(callback: CallbackQuery) -> None:
    try:
        room_id = int((callback.data or "").rsplit(":", 1)[-1])
        async with get_session_factory()() as session:
            room, players = await get_room_snapshot(session, room_id)
        if callback.message and isinstance(callback.message, Message):
            try:
                await callback.message.edit_text(
                    room_text(room, players), reply_markup=room_keyboard(room_id)
                )
            except TelegramBadRequest as exc:
                # Telegram raises this when the refreshed content is unchanged.
                if "message is not modified" not in str(exc).lower():
                    raise
        await callback.answer("Xona yangilandi.")
    except RoomError as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer("Xonani yangilab bo‘lmadi.", show_alert=True)
        raise


@router.callback_query(F.data.startswith("room:leave:"))
async def leave_room_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Foydalanuvchi aniqlanmadi.", show_alert=True)
        return
    try:
        room_id = int((callback.data or "").rsplit(":", 1)[-1])
        async with get_session_factory()() as session:
            async with session.begin():
                code = await leave_room(session, callback.from_user.id, room_id)
        await callback.answer("Xonadan chiqdingiz.")
        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(f"🚪 Siz <code>{escape(code)}</code> xonasidan chiqdingiz.")
    except RoomError as exc:
        await callback.answer(str(exc), show_alert=True)
