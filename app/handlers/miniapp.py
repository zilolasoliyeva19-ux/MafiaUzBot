from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.config import get_settings
from app.database import get_session_factory
from app.services.rooms import RoomError, create_room, list_public_rooms, register_user
from app.handlers.rooms import room_keyboard, room_text

router = Router(name="miniapp")

MINI_APP_URL = "https://mafiauzbot-production.up.railway.app"
BOT_URL = "https://t.me/MafiaJaneUzbot"


def miniapp_keyboard(private: bool = True) -> InlineKeyboardMarkup:
    if private:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ MafiaUz Mini App’ni ochish", web_app=WebAppInfo(url=MINI_APP_URL))],
            [InlineKeyboardButton(text="👥 Guruhga qo‘shish", url=f"https://t.me/MafiaJaneUzbot?startgroup=play")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 Botni shaxsiy chatda ochish", url=BOT_URL)],
        [InlineKeyboardButton(text="➕ Botni guruhga qo‘shish", url="https://t.me/MafiaJaneUzbot?startgroup=play")],
    ])


def group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Xona yaratish", callback_data="group:create"),
         InlineKeyboardButton(text="🎮 Ochiq xonalar", callback_data="group:rooms")],
        [InlineKeyboardButton(text="📜 Qoidalar", callback_data="group:rules"),
         InlineKeyboardButton(text="🤖 Solo Game", url=f"{BOT_URL}?start=solo")],
        [InlineKeyboardButton(text="🌐 Mini App / Profil / Shop", url=BOT_URL)],
    ])


@router.message(Command("app"))
async def open_miniapp(message: Message) -> None:
    is_private = bool(message.chat and message.chat.type == "private")
    if not is_private:
        await message.answer(
            "🌐 Mini App Telegram’da shaxsiy chatda ochiladi. Quyidagi tugmani bosing, "
            "yoki guruhda /group buyrug‘i bilan o‘yin menyusini oching.",
            reply_markup=miniapp_keyboard(private=False),
        )
        return
    await message.answer(
        "🌌 <b>MAFIA UZ MINI APP</b>\n\n"
        "Zamonaviy o‘yin menyusi, xonalar, profil va Shop.\n"
        "Eslatma: Mini App’ning ayrim ko‘rsatkichlari hozircha demo ma’lumotlardan foydalanadi.",
        reply_markup=miniapp_keyboard(private=True),
    )


@router.message(Command("group"))
async def group_menu(message: Message) -> None:
    await message.answer(
        "🎭 <b>MAFIA UZ — GURUH MENYUSI</b>\n\n"
        "Guruhda xona yaratish, ochiq xonalarni ko‘rish yoki qoidalarni ochish uchun tugmani tanlang.\n"
        "Buyruqlar: /create · /play · /join KOD · /leave · /rules",
        reply_markup=group_keyboard(),
    )


@router.callback_query(F.data == "group:menu")
async def group_menu_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(
            "🎭 <b>MAFIA UZ — GURUH MENYUSI</b>\\n\\n"
            "Xona yaratish, ochiq xonalarni ko‘rish yoki qoidalarni ochish uchun tugmani tanlang.",
            reply_markup=group_keyboard(),
        )
    await callback.answer()

@router.callback_query(F.data == "group:create")
async def group_create_room(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer("Foydalanuvchini aniqlab bo‘lmadi.", show_alert=True)
        return
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                user = callback.from_user
                display_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
                await register_user(session, user.id, user.username, display_name or user.full_name)
                settings = get_settings()
                room = await create_room(
                    session,
                    user.id,
                    is_public=True,
                    min_players=settings.min_players,
                    max_players=settings.max_players,
                )
                room_id = room.id
                room_code = room.room_code
        await callback.answer("Xona yaratildi!")
        await callback.message.answer(
            f"🏠 <b>Guruh xonasi yaratildi!</b>\n"
            f"Yaratuvchi: {escape(callback.from_user.full_name)}\n"
            f"Xona kodi: <code>{escape(room_code)}</code>\n\n"
            f"Do‘stlar qo‘shilishi uchun: <code>/join {escape(room_code)}</code>",
        )
        async with get_session_factory()() as session:
            from app.services.rooms import get_room_snapshot
            room, players = await get_room_snapshot(session, room_id)
        await callback.message.answer(room_text(room, players), reply_markup=room_keyboard(room_id))
    except RoomError as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer("Xona yaratishda xatolik. Keyinroq urinib ko‘ring.", show_alert=True)
        raise


@router.callback_query(F.data == "group:rooms")
async def group_list_rooms(callback: CallbackQuery) -> None:
    try:
        async with get_session_factory()() as session:
            rooms = await list_public_rooms(session)
        if not rooms:
            await callback.answer("Hozir ochiq xona yo‘q.", show_alert=True)
            return
        rows = [
            [InlineKeyboardButton(
                text=f"🚪 {room.room_code} · {count}/{room.max_players}",
                callback_data=f"room:join:{room.room_code}",
            )]
            for room, count in rooms[:10]
        ]
        await callback.message.answer("🎮 <b>Ochiq Mafia xonalari</b>\nQo‘shilish uchun tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await callback.answer()
    except Exception:
        await callback.answer("Xonalarni yuklab bo‘lmadi.", show_alert=True)
        raise


@router.callback_query(F.data == "group:rules")
async def group_rules(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "📜 <b>Mafia qoidalari</b>\n\n"
        "• Tunda maxsus rollar harakat qiladi.\n"
        "• Kunduz tirik o‘yinchilar muhokama qiladi va ovoz beradi.\n"
        "• Shahar mafiyani topsa — shahar g‘alaba qiladi.\n"
        "• Mafiya son jihatdan tenglashsa yoki ustun bo‘lsa — mafiya g‘alaba qiladi."
    )
    await callback.answer()
