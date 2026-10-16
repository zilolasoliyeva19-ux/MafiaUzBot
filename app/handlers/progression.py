from __future__ import annotations

import json
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database import get_session_factory
from app.models import BotSetting, User

router = Router(name="progression")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _season() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _value(session, key: str, default: str = "0") -> str:
    row = await session.get(BotSetting, key)
    return row.value if row else default


async def _set(session, key: str, value: str) -> None:
    row = await session.get(BotSetting, key)
    if row is None:
        session.add(BotSetting(key=key, value=value))
    else:
        row.value = value


async def _add_coins(session, user_id: int, amount: int) -> int:
    key = f"u:{user_id}:coins"
    current = int(await _value(session, key, "100"))
    new_balance = max(0, current + amount)
    await _set(session, key, str(new_balance))
    return new_balance


def _xp(user: User) -> int:
    return user.games_played * 10 + user.wins * 25


async def record_match_progress(session, user_id: int, won: bool) -> None:
    """Record daily and monthly-season progress in the existing BotSetting store."""
    day = _today()
    month = _season()
    for suffix in (f"daily:{day}:games", f"season:{month}:games"):
        key = f"u:{user_id}:{suffix}"
        await _set(session, key, str(int(await _value(session, key, "0")) + 1))
    if won:
        for suffix in (f"daily:{day}:wins", f"season:{month}:wins"):
            key = f"u:{user_id}:{suffix}"
            await _set(session, key, str(int(await _value(session, key, "0")) + 1))


def _daily_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Kunlik sovg‘ani olish", callback_data="progress:daily:gift")],
        [
            InlineKeyboardButton(text="🎮 1 o‘yin · +15 🪙", callback_data="progress:daily:play"),
            InlineKeyboardButton(text="🏆 1 g‘alaba · +25 🪙", callback_data="progress:daily:win"),
        ],
    ])


@router.message(Command("daily"))
@router.message(F.text == "🎁 Kunlik sovg‘a")
async def daily_menu(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    day = _today()
    async with get_session_factory()() as session:
        games = int(await _value(session, f"u:{uid}:daily:{day}:games"))
        wins = int(await _value(session, f"u:{uid}:daily:{day}:wins"))
        raw_claims = await _value(session, f"u:{uid}:daily_claims:{day}", "[]")
        try:
            claims = json.loads(raw_claims)
        except (TypeError, json.JSONDecodeError):
            claims = []
    gift_status = "olingan" if "gift" in claims else "tayyor"
    play_status = "bajarildi" if games >= 1 else "bajarilmadi"
    win_status = "bajarildi" if wins >= 1 else "bajarilmadi"
    await message.answer(
        "🎁 <b>KUNLIK TOPSHIRIQLAR</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<blockquote>Har kuni kirib sovg‘a ol va yangi maqsadlarni bajargin.</blockquote>\n"
        f"📅 Sana (UTC): <code>{day}</code>\n\n"
        f"🎁 Kunlik sovg‘a: <b>{gift_status}</b> · +25 🪙\n"
        f"🎮 Bugungi o‘yinlar: <b>{games}/1</b> · {play_status} · +15 🪙\n"
        f"🏆 Bugungi g‘alabalar: <b>{wins}/1</b> · {win_status} · +25 🪙\n\n"
        "Topshiriq mukofoti har kuni bir marta olinadi.",
        reply_markup=_daily_keyboard(),
    )


@router.callback_query(F.data.startswith("progress:daily:"))
async def daily_claim(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    task = (callback.data or "").rsplit(":", 1)[-1]
    uid = callback.from_user.id
    day = _today()
    rewards = {"gift": (25, None), "play": (15, f"u:{uid}:daily:{day}:games"), "win": (25, f"u:{uid}:daily:{day}:wins")}
    if task not in rewards:
        await callback.answer("Topshiriq topilmadi.", show_alert=True)
        return
    reward, progress_key = rewards[task]
    async with get_session_factory()() as session:
        async with session.begin():
            claims_key = f"u:{uid}:daily_claims:{day}"
            try:
                claims = json.loads(await _value(session, claims_key, "[]"))
            except (TypeError, json.JSONDecodeError):
                claims = []
            if task in claims:
                result = "Bu mukofotni bugun oldingiz."
            elif progress_key and int(await _value(session, progress_key)) < 1:
                result = "Avval topshiriqni bajaring, keyin mukofotni oling."
            else:
                claims.append(task)
                await _set(session, claims_key, json.dumps(claims))
                balance = await _add_coins(session, uid, reward)
                result = f"🎉 +{reward} 🪙 olindi! Balans: {balance} 🪙"
    await callback.answer(result, show_alert=True)
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=_daily_keyboard())
        except Exception:
            pass


@router.message(Command("achievements"))
@router.message(F.text == "🏅 Yutuqlar")
async def achievements(message: Message) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Avval /start buyrug‘ini yuboring.")
        return
    xp = _xp(user)
    badges = [
        ("🎮 Birinchi o‘yin", user.games_played >= 1),
        ("🏆 Birinchi g‘alaba", user.wins >= 1),
        ("🔥 10 g‘alaba", user.wins >= 10),
        ("🎖️ 25 o‘yin", user.games_played >= 25),
        ("👑 50 g‘alaba", user.wins >= 50),
        ("⭐ 1000 XP", xp >= 1000),
    ]
    lines = [f"{'✅' if earned else '🔒'} {name}" for name, earned in badges]
    await message.answer(
        "🏅 <b>YUTUQLAR</b>\n\n" + "\n".join(lines) +
        f"\n\n⭐ Jami XP: <b>{xp}</b>",
    )


_BATTLEPASS_TIERS = [(100, 25), (250, 50), (500, 100), (800, 150), (1200, 250)]


def _battlepass_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎁 {xp} XP · {coins} 🪙", callback_data=f"progress:bp:{i}")]
        for i, (xp, coins) in enumerate(_BATTLEPASS_TIERS, 1)
    ])


@router.message(Command("battlepass"))
@router.message(F.text == "🎟️ Battle Pass")
async def battlepass(message: Message) -> None:
    if not message.from_user:
        return
    async with get_session_factory()() as session:
        user = await session.get(User, message.from_user.id)
        raw_claims = await _value(session, f"u:{message.from_user.id}:bp_claims:{_season()}", "[]")
    if not user:
        await message.answer("Avval /start buyrug‘ini yuboring.")
        return
    try:
        claims = json.loads(raw_claims)
    except (TypeError, json.JSONDecodeError):
        claims = []
    xp = _xp(user)
    tiers = "\n".join(
        f"{'✅' if str(i) in claims else ('🎁' if xp >= needed else '🔒')} {needed} XP → {coins} 🪙"
        for i, (needed, coins) in enumerate(_BATTLEPASS_TIERS, 1)
    )
    await message.answer(
        f"🎟️ <b>BATTLE PASS · {_season()}</b>\n"
        f"⭐ XP: <b>{xp}</b>\n\n{tiers}\n\n"
        "Mukofotni olish uchun tegishli tugmani bosing. Har bir bosqich faqat bir marta olinadi.",
        reply_markup=_battlepass_keyboard(),
    )


@router.callback_query(F.data.startswith("progress:bp:"))
async def battlepass_claim(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    try:
        tier = int((callback.data or "").rsplit(":", 1)[-1])
        needed, reward = _BATTLEPASS_TIERS[tier - 1]
    except (ValueError, IndexError):
        await callback.answer("Battle Pass bosqichi noto‘g‘ri.", show_alert=True)
        return
    uid = callback.from_user.id
    month = _season()
    async with get_session_factory()() as session:
        async with session.begin():
            user = await session.get(User, uid)
            if not user:
                await callback.answer("Avval /start buyrug‘ini yuboring.", show_alert=True)
                return
            if _xp(user) < needed:
                result = f"Bu bosqich uchun {needed} XP kerak."
            else:
                key = f"u:{uid}:bp_claims:{month}"
                try:
                    claims = json.loads(await _value(session, key, "[]"))
                except (TypeError, json.JSONDecodeError):
                    claims = []
                if str(tier) in claims:
                    result = "Bu mukofotni allaqachon olgansiz."
                else:
                    claims.append(str(tier))
                    await _set(session, key, json.dumps(claims))
                    balance = await _add_coins(session, uid, reward)
                    result = f"🎉 Battle Pass mukofoti: +{reward} 🪙. Balans: {balance} 🪙"
    await callback.answer(result, show_alert=True)


@router.message(Command("season"))
@router.message(F.text == "🌟 Mavsum")
async def season_leaderboard(message: Message) -> None:
    month = _season()
    async with get_session_factory()() as session:
        rows = list((await session.scalars(
            select(BotSetting).where(BotSetting.key.like(f"u:%:season:{month}:wins"))
        )).all())
        ranking = []
        for row in rows:
            try:
                user_id = int(row.key.split(":")[1])
                wins = int(row.value)
            except (ValueError, IndexError):
                continue
            user = await session.get(User, user_id)
            if user:
                ranking.append((wins, user.games_played, user.display_name))
    ranking.sort(key=lambda item: (item[0], item[1]), reverse=True)
    lines = [
        f"{['🥇','🥈','🥉'][i] if i < 3 else str(i + 1) + '.'} {name} — <b>{wins}</b> g‘alaba"
        for i, (wins, _, name) in enumerate(ranking[:10])
    ]
    await message.answer(
        f"🌟 <b>MAVSUM REYTINGI · {month}</b>\n\n" +
        ("\n".join(lines) if lines else "Bu mavsumda natijalar hali yo‘q. Birinchi bo‘lib o‘yna!"),
    )
