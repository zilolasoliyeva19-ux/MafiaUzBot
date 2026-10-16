import json
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from app.database import get_session_factory
from app.models import BotSetting, User
from app.services.rooms import register_user

router = Router(name="friends")


async def _read_list(session, key: str) -> list[int]:
    row = await session.get(BotSetting, key)
    if not row:
        return []
    try:
        values = json.loads(row.value)
        return [int(value) for value in values]
    except (ValueError, TypeError, json.JSONDecodeError):
        return []


async def _write_list(session, key: str, values: list[int]) -> None:
    row = await session.get(BotSetting, key)
    payload = json.dumps(list(dict.fromkeys(values)))
    if row is None:
        session.add(BotSetting(key=key, value=payload))
    else:
        row.value = payload


@router.message(Command("friends"))
@router.message(lambda message: message.text == "👥 Do‘stlar")
async def show_friends(message: Message) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        ids = await _read_list(session, f"u:{message.from_user.id}:friends")
        users = []
        for friend_id in ids:
            friend = await session.get(User, friend_id)
            if friend:
                users.append(friend)
    lines = [f"• {escape(user.display_name)} · <code>{user.telegram_id}</code>" for user in users]
    await message.answer(
        "👥 <b>DO‘STLAR RO‘YXATI</b>\n\n"
        + ("\n".join(lines) if lines else "Ro‘yxat bo‘sh. /friendadd @username orqali taklif yuboring.")
        + "\n\n"
        "➕ Qo‘shish: <code>/friendadd @username</code>\n"
        "✅ Qabul qilish: <code>/friendaccept TELEGRAM_ID</code>\n"
        "➖ O‘chirish: <code>/friendremove TELEGRAM_ID</code>"
    )


@router.message(Command("friendadd"))
async def request_friend(message: Message, command: CommandObject) -> None:
    if not message.from_user:
        return
    username = (command.args or "").strip().lstrip("@")
    if not username:
        await message.answer("Foydalanish: <code>/friendadd @username</code>")
        return
    async with get_session_factory()() as session:
        async with session.begin():
            await register_user(session, message.from_user.id, message.from_user.username, message.from_user.full_name)
            target = await session.scalar(select(User).where(User.username == username))
            if not target:
                result = "Bu username topilmadi. Do‘stingiz avval botga /start yuborishi kerak."
                target_id = None
            elif target.telegram_id == message.from_user.id:
                result = "O‘zingizni do‘st sifatida qo‘sha olmaysiz."
                target_id = None
            else:
                friends = await _read_list(session, f"u:{message.from_user.id}:friends")
                if target.telegram_id in friends:
                    result = "Bu foydalanuvchi allaqachon do‘stlaringiz ro‘yxatida."
                    target_id = None
                else:
                    requests = await _read_list(session, f"u:{target.telegram_id}:friend_requests")
                    if message.from_user.id not in requests:
                        requests.append(message.from_user.id)
                        await _write_list(session, f"u:{target.telegram_id}:friend_requests", requests)
                    result = f"👋 {escape(target.display_name)} ga do‘stlik so‘rovi yuborildi."
                    target_id = target.telegram_id
    await message.answer(result)
    if target_id:
        try:
            await message.bot.send_message(
                target_id,
                f"👥 <b>Do‘stlik so‘rovi</b>\n{escape(message.from_user.full_name)} sizni do‘stlarga qo‘shmoqchi.\n"
                f"Qabul qilish: <code>/friendaccept {message.from_user.id}</code>",
            )
        except Exception:
            pass


@router.message(Command("friendaccept"))
async def accept_friend(message: Message, command: CommandObject) -> None:
    if not message.from_user:
        return
    try:
        requester_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Foydalanish: <code>/friendaccept TELEGRAM_ID</code>")
        return
    uid = message.from_user.id
    async with get_session_factory()() as session:
        async with session.begin():
            requests = await _read_list(session, f"u:{uid}:friend_requests")
            requester = await session.get(User, requester_id)
            if requester_id not in requests or requester is None:
                result = "Bu foydalanuvchidan kutilayotgan so‘rov topilmadi."
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
                result = f"✅ {escape(requester.display_name)} do‘stlaringizga qo‘shildi."
    await message.answer(result)


@router.message(Command("friendremove"))
async def remove_friend(message: Message, command: CommandObject) -> None:
    if not message.from_user:
        return
    try:
        friend_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Foydalanish: <code>/friendremove TELEGRAM_ID</code>")
        return
    uid = message.from_user.id
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
    await message.answer(result)
