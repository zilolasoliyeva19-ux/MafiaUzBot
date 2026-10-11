import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from app.config import get_settings
from app.database import get_session_factory
from app.models import AdminAuditLog, GameMatch, GameRoom, User

router = Router(name="admin")


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats")],
        [InlineKeyboardButton(text="❔ Buyruqlar", callback_data="admin:help")],
    ])


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Bu bo‘lim faqat administratorlar uchun.")
        return
    await message.answer(
        "🛠️ <b>MafiaUzBot — Admin panel</b>\n\n"
        "Bu panel orqali bot statistikasi, balanslar va e’lonlarni boshqarishingiz mumkin.",
        reply_markup=_keyboard(),
    )


@router.callback_query(F.data.startswith("admin:"))
async def admin_actions(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return
    action = (callback.data or "").split(":", 1)[1]
    if action == "stats":
        async with get_session_factory()() as session:
            users = await session.scalar(select(func.count()).select_from(User)) or 0
            rooms = await session.scalar(select(func.count()).select_from(GameRoom)) or 0
            active_rooms = await session.scalar(select(func.count()).select_from(GameRoom).where(GameRoom.status == "active")) or 0
            matches = await session.scalar(select(func.count()).select_from(GameMatch)) or 0
            wins = await session.scalar(select(func.sum(User.wins))) or 0
        text = (f"📊 <b>Bot statistikasi</b>\n\n👥 Foydalanuvchilar: <b>{users}</b>\n"
                f"🏠 Xonalar: <b>{rooms}</b>\n🎮 Faol xonalar: <b>{active_rooms}</b>\n"
                f"🎲 Jami matchlar: <b>{matches}</b>\n🏆 Jami g‘alabalar: <b>{wins}</b>")
        await callback.answer()
        if callback.message:
            await callback.message.answer(text, reply_markup=_keyboard())
        return
    if action == "help":
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "🧾 <b>Admin buyruqlari</b>\n"
                "/admin — panel\n"
                "/broadcast MATN — barcha foydalanuvchilarga xabar yuborish\n"
                "/coins TELEGRAM_ID MIQDOR — balansni o‘zgartirish (manfiy son ham mumkin).",
                reply_markup=_keyboard(),
            )
        return
    await callback.answer("Noma’lum amal.", show_alert=True)


@router.message(Command("coins"))
async def admin_coins(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Foydalanish: <code>/coins TELEGRAM_ID MIQDOR</code>")
        return
    try:
        target_id, delta = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("ID va miqdor butun son bo‘lishi kerak.")
        return
    async with get_session_factory()() as session:
        async with session.begin():
            user = await session.get(User, target_id)
            if not user:
                await message.answer("Foydalanuvchi topilmadi.")
                return
            key = f"u:{target_id}:coins"
            row = await session.get(BotSetting, key)
            old = int(row.value) if row else 100
            new = max(0, old + delta)
            if row is None:
                session.add(BotSetting(key=key, value=str(new)))
            else:
                row.value = str(new)
            session.add(AdminAuditLog(admin_id=message.from_user.id, action="adjust_coins",
                                      target_id=target_id, details=f"{old}->{new}"))
    await message.answer(f"✅ <code>{target_id}</code> balans: <b>{new} 🪙</b>")


@router.message(Command("broadcast"))
async def admin_broadcast(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return
    body = (message.text or "").partition(" ")[2].strip()
    if not body:
        await message.answer("Foydalanish: <code>/broadcast Xabar matni</code>")
        return
    async with get_session_factory()() as session:
        ids = list((await session.scalars(select(User.telegram_id))).all())
    sent = failed = 0
    for user_id in ids:
        try:
            await message.bot.send_message(user_id, body)
            sent += 1
        except Exception:
            failed += 1
    async with get_session_factory()() as session:
        async with session.begin():
            session.add(AdminAuditLog(admin_id=message.from_user.id, action="broadcast",
                                      details=json.dumps({"sent": sent, "failed": failed}, ensure_ascii=False)))
    await message.answer(f"📣 Yuborish yakunlandi. Yetkazildi: <b>{sent}</b>, xato: <b>{failed}</b>.")
