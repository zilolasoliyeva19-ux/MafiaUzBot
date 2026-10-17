import json
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database import get_session_factory
from app.models import BotSetting, User
from app.services.rooms import register_user

router = Router(name="friends")


class PendingFriendInput(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.from_user or not message.text or message.text.startswith("/"):
            return False
        async with get_session_factory()() as session:
            row = await session.get(BotSetting, f"u:{message.from_user.id}:friend_pending")
            return bool(row and row.value == "add")


async def _read_list(session, key: str) -> list[int]:
    row = await session.get(BotSetting, key)
    if not row:
        return []
    try:
        return [int(value) for value in json.loads(row.value)]
    except (ValueError, TypeError, json.JSONDecodeError):
        return []


async def _write_list(session, key: str, values: list[int]) -> None:
    payload = json.dumps(list(dict.fromkeys(values)))
    row = await session.get(BotSetting, key)
    if row is None:
        session.add(BotSetting(key=key, value=payload))
    else:
        row.value = payload


async def _set_pending(session, uid: int, action: str) -> None:
    key = f"u:{uid}:friend_pending"
    row = await session.get(BotSetting, key)
    if row is None:
        session.add(BotSetting(key=key, value=action))
    else:
        row.value = action


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Do‘st qo‘shish", callback_data="friends:add")],
        [InlineKeyboardButton(text="📨 So‘rovlar", callback_data="friends:requests"),
         InlineKeyboardButton(text="👥 Do‘stlarim", callback_data="friends:list")],
        [InlineKeyboardButton(text="ℹ️ Maxfiylik", callback_data="friends:privacy")],
    ])


@router.message(Command("friends"))
@router.message(F.text == "👥 Do‘stlar")
async def show_friends(message: Message) -> None:
    await message.answer(
        "👥 <b>DO‘STLAR MARKAZI</b>\n"
        "<blockquote>Do‘stlik so‘rovlari va ro‘yxatingizni shu yerdan boshqaring.</blockquote>\n\n"
        "🔐 Faqat siz boshlagan yoki qabul qilgan so‘rovlar ko‘rinadi.\n"
        "🛡️ Telegram ID va username ommaviy reytingda ko‘rsatilmaydi.",
        reply_markup=_menu_keyboard(),
    )


@router.callback_query(F.data == "friends:add")
async def begin_add(callback: CallbackQuery) -> None:
    async with get_session_factory()() as session:
        async with session.begin():
            await _set_pending(session, callback.from_user.id, "add")
    await callback.answer()
    if callback.message:
        await callback.message.answer("➕ Do‘stingizning @username’ini yuboring. Bekor qilish uchun /cancel yuboring.")


@router.callback_query(F.data == "friends:list")
async def friends_list(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    async with get_session_factory()() as session:
        ids = await _read_list(session, f"u:{uid}:friends")
        users = [await session.get(User, friend_id) for friend_id in ids]
    rows = []
    lines = []
    for user in users:
        if not user:
            continue
        lines.append(f"• {escape(user.display_name)}")
        rows.append([InlineKeyboardButton(
            text=f"➖ {user.display_name[:40]}",
            callback_data=f"friends:remove:{user.telegram_id}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="friends:home")])
    if callback.message:
        await callback.message.answer(
            "👥 <b>DO‘STLARIM</b>\n\n" + ("\n".join(lines) if lines else "Ro‘yxatingiz hozircha bo‘sh."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await callback.answer()


@router.callback_query(F.data == "friends:requests")
async def friend_requests(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    async with get_session_factory()() as session:
        ids = await _read_list(session, f"u:{uid}:friend_requests")
        users = [await session.get(User, requester_id) for requester_id in ids]
    rows = []
    lines = []
    for user in users:
        if not user:
            continue
        lines.append(f"• {escape(user.display_name)}")
        rows.append([InlineKeyboardButton(
            text=f"✅ Qabul qilish: {user.display_name[:35]}",
            callback_data=f"friends:accept:{user.telegram_id}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="friends:home")])
    if callback.message:
        await callback.message.answer(
            "📨 <b>KELGAN SO‘ROVLAR</b>\n\n" + ("\n".join(lines) if lines else "Yangi so‘rov yo‘q."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await callback.answer()


@router.callback_query(F.data == "friends:home")
async def friends_home(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("👥 <b>Do‘stlar markazi</b>", reply_markup=_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "friends:privacy")
async def friends_privacy(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(
            "🔐 <b>MAXFIYLIK QOIDALARI</b>\n\n"
            "• Do‘stlar ro‘yxati faqat o‘zingizga ko‘rinadi.\n"
            "• Do‘stlik so‘rovi qabul qilinmaguncha ikki tomon do‘st bo‘lmaydi.\n"
            "• Ommaviy reytingda Telegram ID va username ko‘rsatilmaydi.\n"
            "• Istalgan vaqtda do‘stni ro‘yxatdan olib tashlashingiz mumkin."
        )
    await callback.answer()


@router.callback_query(F.data.startswith("friends:accept:"))
async def accept_friend(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    try:
        requester_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("So‘rov noto‘g‘ri.", show_alert=True)
        return
    async with get_session_factory()() as session:
        async with session.begin():
            requests = await _read_list(session, f"u:{uid}:friend_requests")
            requester = await session.get(User, requester_id)
            me = await session.get(User, uid)
            if requester_id not in requests or requester is None:
                result = "Bu so‘rov topilmadi yoki allaqachon ko‘rib chiqilgan."
            else:
                my_friends = await _read_list(session, f"u:{uid}:friends")
                their_friends = await _read_list(session, f"u:{requester_id}:friends")
                if requester_id not in my_friends:
                    my_friends.append(requester_id)
                if uid not in their_friends:
                    their_friends.append(uid)
                requests.remove(requester_id)
                await _write_list(session, f"u:{uid}:friends", my_friends)
                await _write_list(session, f"u:{requester_id}:friends", their_friends)
                await _write_list(session, f"u:{uid}:friend_requests", requests)
                result = f"✅ {escape(requester.display_name)} endi do‘stlaringiz ro‘yxatida."
    await callback.answer(result, show_alert=True)
    if callback.message:
        await callback.message.answer(result, reply_markup=_menu_keyboard())
    try:
        await callback.bot.send_message(requester_id, "✅ Do‘stlik so‘rovingiz qabul qilindi! Endi do‘st bo‘ldingiz.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("friends:remove:"))
async def remove_friend(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    try:
        friend_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Foydalanuvchi noto‘g‘ri.", show_alert=True)
        return
    async with get_session_factory()() as session:
        async with session.begin():
            mine = await _read_list(session, f"u:{uid}:friends")
            theirs = await _read_list(session, f"u:{friend_id}:friends")
            if friend_id not in mine:
                result = "Bu foydalanuvchi do‘stlaringiz ro‘yxatida yo‘q."
            else:
                mine.remove(friend_id)
                theirs = [item for item in theirs if item != uid]
                await _write_list(session, f"u:{uid}:friends", mine)
                await _write_list(session, f"u:{friend_id}:friends", theirs)
                result = "➖ Do‘st ro‘yxatdan olib tashlandi."
    await callback.answer(result, show_alert=True)
    if callback.message:
        await callback.message.answer(result, reply_markup=_menu_keyboard())
    try:
        await callback.bot.send_message(friend_id, "ℹ️ Siz bilan do‘stlik aloqasi yangilandi.")
    except Exception:
        pass


@router.message(Command("cancel"))
async def cancel_pending(message: Message) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        async with session.begin():
            await _set_pending(session, message.from_user.id, "")
    await message.answer("Bekor qilindi.", reply_markup=_menu_keyboard())


@router.message(PendingFriendInput())
async def process_friend_input(message: Message) -> None:
    if not message.from_user or not message.text:
        return
    uid = message.from_user.id
    username = message.text.strip().lstrip("@")
    async with get_session_factory()() as session:
        async with session.begin():
            pending = await session.get(BotSetting, f"u:{uid}:friend_pending")
            if not pending or pending.value != "add":
                return
            pending.value = ""
            await register_user(session, uid, message.from_user.username, message.from_user.full_name)
            target = await session.scalar(select(User).where(User.username == username))
            if not target:
                result, target_id = "Bu username topilmadi. Do‘stingiz avval botga /start yuborgan bo‘lishi kerak.", None
            elif target.telegram_id == uid:
                result, target_id = "O‘zingizni do‘st sifatida qo‘sha olmaysiz.", None
            else:
                mine = await _read_list(session, f"u:{uid}:friends")
                requests = await _read_list(session, f"u:{target.telegram_id}:friend_requests")
                if target.telegram_id in mine:
                    result, target_id = "Bu foydalanuvchi allaqachon do‘stlaringiz ro‘yxatida.", None
                elif uid in requests:
                    result, target_id = "So‘rov allaqachon yuborilgan.", None
                else:
                    requests.append(uid)
                    await _write_list(session, f"u:{target.telegram_id}:friend_requests", requests)
                    result, target_id = f"📨 So‘rov yuborildi: {escape(target.display_name)}.", target.telegram_id
    await message.answer(result, reply_markup=_menu_keyboard())
    if target_id:
        try:
            await message.bot.send_message(
                target_id,
                f"👥 <b>Yangi do‘stlik so‘rovi</b>\n{escape(message.from_user.full_name)} sizni do‘stlarga qo‘shmoqchi.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"friends:accept:{uid}")],
                    [InlineKeyboardButton(text="❌ E’tibor bermaslik", callback_data="friends:requests")],
                ]),
            )
        except Exception:
            pass
