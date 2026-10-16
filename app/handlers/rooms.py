import asyncio
import time
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



GROUP_LOBBIES: dict[int, dict] = {}
ROOM_EXPIRY_TASKS: dict[int, asyncio.Task] = {}


async def _expire_idle_room(bot, room_id: int, owner_id: int) -> None:
    """Close a private/public lobby after five minutes if it never fills enough to start."""
    try:
        await asyncio.sleep(300)
        expired = False
        minimum = 4
        async with get_session_factory()() as session:
            async with session.begin():
                room = await session.get(GameRoom, room_id, with_for_update=True)
                if room is None or room.status != "lobby":
                    return
                minimum = room.min_players
                _, players = await get_room_snapshot(session, room_id)
                if len(players) < minimum:
                    room.status = "cancelled"
                    expired = True
        if expired:
            try:
                await bot.send_message(
                    owner_id,
                    "⌛ <b>MAFIA UZ · XONA YOPILDI</b>\n\n"
                    f"Xonada {minimum} nafar o‘yinchi yig‘ilmadi, shuning uchun 5 daqiqadan so‘ng avtomatik yopildi.\n"
                    "🎮 Yangi xona ochish uchun /create buyrug‘ini yuboring."
                )
            except Exception:
                pass
    except asyncio.CancelledError:
        raise
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Room expiry failed for room %s", room_id)
    finally:
        ROOM_EXPIRY_TASKS.pop(room_id, None)


def group_game_keyboard(room_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 O‘yinga qo‘shilish", callback_data=f"groupgame:join:{room_id}")],
        [InlineKeyboardButton(text="🔄 Ishtirokchilarni yangilash", callback_data=f"groupgame:refresh:{room_id}")],
    ])


def group_lobby_text(room: GameRoom, players: list, seconds_left: int) -> str:
    lines = []
    for player in players:
        crown = " 👑" if player.telegram_id == room.owner_id else ""
        lines.append(f"• {escape(player.display_name)}{crown}")
    roster = "\n".join(lines) or "Hali hech kim qo‘shilmadi"
    minutes, seconds = divmod(max(0, seconds_left), 60)
    count = len(players)
    status = "✅ Yetarli o‘yinchi yig‘ildi" if count >= room.min_players else f"⏳ Kamida {room.min_players} kishi kerak"
    return (
        "🎭 <b>MAFIA UZ · GURUH O‘YINI</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🏠 Xona: <code>{escape(room.room_code)}</code>\n"
        f"👥 O‘yinchilar: <b>{count}/{room.max_players}</b>\n"
        f"⏱️ Boshlanishigacha: <b>{minutes}:{seconds:02d}</b>\n"
        f"{status}\n\n"
        "<b>Stol atrofida:</b>\n" + roster + "\n\n"
        "👇 Quyidagi tugmani bosib o‘yinga qo‘shiling.\n"
        "🔐 Rollar o‘yin boshlanganda botning shaxsiy chatida yuboriladi. Botni avval /start bilan ochib qo‘ying."
    )


async def _group_game_countdown(bot, room_id: int) -> None:
    lobby = GROUP_LOBBIES.get(room_id)
    if not lobby:
        return
    try:
        while True:
            remaining = int(max(0, lobby["deadline"] - time.monotonic()))
            async with get_session_factory()() as session:
                room, players = await get_room_snapshot(session, room_id)
                if room.status != "lobby":
                    return
                count = len(players)
            try:
                await bot.edit_message_text(
                    chat_id=lobby["chat_id"],
                    message_id=lobby["message_id"],
                    text=group_lobby_text(room, players, remaining),
                    reply_markup=group_game_keyboard(room_id),
                )
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
            if remaining <= 0:
                break
            await asyncio.sleep(min(15, remaining))

        async with get_session_factory()() as session:
            room, players = await get_room_snapshot(session, room_id)
            count = len(players)
        if count < room.min_players:
            async with get_session_factory()() as session:
                async with session.begin():
                    locked = await session.get(GameRoom, room_id, with_for_update=True)
                    if locked and locked.status == "lobby":
                        locked.status = "cancelled"
            await bot.edit_message_text(
                chat_id=lobby["chat_id"],
                message_id=lobby["message_id"],
                text=(
                    "⌛ <b>Vaqt tugadi!</b>\n\n"
                    f"O‘yinni boshlash uchun kamida <b>{room.min_players} kishi</b> kerak edi, "
                    f"ammo {count} kishi yig‘ildi. Yangi /game bilan qayta boshlashingiz mumkin."
                ),
            )
            return

        from app.handlers.gameplay import start_room_game
        ok, result = await start_room_game(bot, room_id)
        await bot.edit_message_text(
            chat_id=lobby["chat_id"],
            message_id=lobby["message_id"],
            text=result if ok else f"⚠️ {escape(result)}",
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Group game countdown failed for room %s", room_id)
        try:
            await bot.send_message(lobby["chat_id"], "⚠️ O‘yinni avtomatik boshlashda xatolik yuz berdi. /game bilan qayta urinib ko‘ring.")
        except Exception:
            pass
    finally:
        GROUP_LOBBIES.pop(room_id, None)


@router.message(Command("game"))
async def group_game_handler(message: Message) -> None:
    if not message.chat or message.chat.type not in {"group", "supergroup"}:
        await message.answer("👥 /game buyrug‘ini guruh chatida yuboring. Mini App’da esa Solo rejimni ochishingiz mumkin.")
        return
    if message.from_user is None:
        return
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                user = message.from_user
                display_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
                await register_user(session, user.id, user.username, display_name or user.full_name)
                settings = get_settings()
                room = await create_room(
                    session, user.id, is_public=True, min_players=4,
                    max_players=max(4, settings.max_players),
                )
                room_id, room_code = room.id, room.room_code
        lobby_message = await message.answer(
            "🎭 <b>MAFIA UZ · GURUH O‘YINI</b>\n\nXona tayyorlanmoqda…",
            reply_markup=group_game_keyboard(room_id),
        )
        GROUP_LOBBIES[room_id] = {
            "chat_id": message.chat.id,
            "message_id": lobby_message.message_id,
            "deadline": time.monotonic() + 90,
        }
        async with get_session_factory()() as session:
            room, players = await get_room_snapshot(session, room_id)
        await lobby_message.edit_text(
            group_lobby_text(room, players, 90),
            reply_markup=group_game_keyboard(room_id),
        )
        GROUP_LOBBIES[room_id]["task"] = asyncio.create_task(
            _group_game_countdown(message.bot, room_id),
            name=f"mafia-group-countdown-{room_id}",
        )
    except RoomError as exc:
        await message.answer(f"⚠️ {escape(str(exc))}")
    except Exception:
        await message.answer("❌ Guruh xonasini yaratib bo‘lmadi. Keyinroq qayta urinib ko‘ring.")
        raise


@router.callback_query(F.data.startswith("groupgame:join:"))
async def group_game_join(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer("Foydalanuvchini aniqlab bo‘lmadi.", show_alert=True)
        return
    try:
        room_id = int((callback.data or "").rsplit(":", 1)[-1])
        async with get_session_factory()() as session:
            async with session.begin():
                room = await session.get(GameRoom, room_id, with_for_update=True)
                if room is None or room.status != "lobby":
                    await callback.answer("Bu xona endi o‘yinchilarni qabul qilmaydi.", show_alert=True)
                    return
                user = callback.from_user
                display_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
                await register_user(session, user.id, user.username, display_name or user.full_name)
                await join_room(session, user.id, room.room_code)
        async with get_session_factory()() as session:
            room, players = await get_room_snapshot(session, room_id)
        lobby = GROUP_LOBBIES.get(room_id, {})
        remaining = int(max(0, lobby.get("deadline", time.monotonic()) - time.monotonic()))
        await callback.message.edit_text(
            group_lobby_text(room, players, remaining),
            reply_markup=group_game_keyboard(room_id),
        )
        await callback.answer("Siz o‘yinga qo‘shildingiz! 🎭")
    except RoomError as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer("Xonaga qo‘shilib bo‘lmadi.", show_alert=True)
        raise


@router.callback_query(F.data.startswith("groupgame:refresh:"))
async def group_game_refresh(callback: CallbackQuery) -> None:
    try:
        room_id = int((callback.data or "").rsplit(":", 1)[-1])
        async with get_session_factory()() as session:
            room, players = await get_room_snapshot(session, room_id)
        lobby = GROUP_LOBBIES.get(room_id, {})
        remaining = int(max(0, lobby.get("deadline", time.monotonic()) - time.monotonic()))
        if callback.message:
            await callback.message.edit_text(
                group_lobby_text(room, players, remaining),
                reply_markup=group_game_keyboard(room_id) if room.status == "lobby" else None,
            )
        await callback.answer("Yangilandi.")
    except RoomError as exc:
        await callback.answer(str(exc), show_alert=True)

def room_keyboard(room_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎭 O‘yinni boshlash (faqat xona egasi)", callback_data=f"game:start:{room_id}")],
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
        f"🎭 <b>MAFIA UZ · KUTISH XONASI</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Xona kodi: <code>{escape(room.room_code)}</code>\n"
        f"👑 Xona egasi: <b>{owner_name}</b>\n"
        f"👥 O‘yinchilar: <b>{actual_count}/{room.max_players}</b>\n"
        f"🎯 Boshlash uchun: <b>{room.min_players} kishi</b>\n"
        "📌 Holat: <b>Kutmoqda</b>\n\n"
        "<blockquote>Do‘stlaringizni taklif qiling va strategiyangizni tayyorlang.</blockquote>\n"
        f"<b>🪑 Ishtirokchilar</b>\n{player_lines}\n\n"
        "▶️ Xona egasi yetarli o‘yinchi yig‘ilgach, <b>O‘yinni boshlash</b> tugmasini bosadi.\n"
        "⌛ Yetarli o‘yinchi 5 daqiqada yig‘ilmasa, xona avtomatik yopiladi."
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
            f"🏠 <b>YANGI MAFIA XONASI</b>\n"
            f"🔑 Xona kodi: <code>{escape(room_code)}</code>\n\n"
            "Do‘stlaringizga kodni yuboring yoki quyidagi xabarni ulashing.\n"
            "⏳ Yetarli o‘yinchi 5 daqiqada yig‘ilmasa, xona avtomatik yopiladi."
        )
        await _show_room(message, room_id)
        old_task = ROOM_EXPIRY_TASKS.pop(room_id, None)
        if old_task:
            old_task.cancel()
        ROOM_EXPIRY_TASKS[room_id] = asyncio.create_task(
            _expire_idle_room(message.bot, room_id, user_id),
            name=f"mafia-room-expiry-{room_id}",
        )
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
