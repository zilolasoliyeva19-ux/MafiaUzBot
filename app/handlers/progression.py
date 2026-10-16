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


_BATTLEPASS_TIERS = [
    {"xp": 100, "free": ("coins", 50), "premium": ("coins", 100)},
    {"xp": 250, "free": ("coins", 100), "premium": ("diamond", 1)},
    {"xp": 500, "free": ("coins", 150), "premium": ("item", "vip_frame")},
    {"xp": 800, "free": ("coins", 250), "premium": ("item", "gold_badge")},
    {"xp": 1200, "free": ("coins", 400), "premium": ("item", "premium_frame")},
]
_FREE_PASS_COST = 500
_PREMIUM_PASS_STARS = 30


def _battlepass_keyboard(free_pass: bool, premium_pass: bool) -> InlineKeyboardMarkup:
    rows = []
    if not free_pass:
        rows.append([InlineKeyboardButton(
            text=f"🟢 Free Pass ochish · {_FREE_PASS_COST} 🪙",
            callback_data="progress:bp:unlock_free",
        )])
    if not premium_pass:
        rows.append([InlineKeyboardButton(
            text=f"💎 Premium Pass · {_PREMIUM_PASS_STARS} ⭐",
            callback_data="stars:buy:battlepass:30",
        )])
    for i, tier in enumerate(_BATTLEPASS_TIERS, 1):
        rows.append([
            InlineKeyboardButton(
                text=f"🟢 Free #{i} · {tier['xp']} XP",
                callback_data=f"progress:bp:free:{i}",
            ),
            InlineKeyboardButton(
                text=f"💎 Premium #{i} · {tier['xp']} XP",
                callback_data=f"progress:bp:premium:{i}",
            ),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("battlepass"))
@router.message(F.text == "🎟️ Battle Pass")
async def battlepass(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    month = _season()
    async with get_session_factory()() as session:
        user = await session.get(User, uid)
        raw_free_claims = await _value(session, f"u:{uid}:bp_free_claims:{month}", "[]")
        raw_premium_claims = await _value(session, f"u:{uid}:bp_premium_claims:{month}", "[]")
        free_pass = await _value(session, f"u:{uid}:bp_free:{month}", "0") == "1"
        premium_pass = await _value(session, f"u:{uid}:bp_premium:{month}", "0") == "1"
        coins = int(await _value(session, f"u:{uid}:coins", "100"))
    if not user:
        await message.answer("Avval /start buyrug‘ini yuboring.")
        return
    try:
        free_claims = json.loads(raw_free_claims)
        premium_claims = json.loads(raw_premium_claims)
    except (TypeError, json.JSONDecodeError):
        free_claims, premium_claims = [], []
    xp = _xp(user)
    lines = []
    for i, tier in enumerate(_BATTLEPASS_TIERS, 1):
        needed = tier["xp"]
        free_reward = tier["free"]
        premium_reward = tier["premium"]
        free_label = f"+{free_reward[1]} 🪙" if free_reward[0] == "coins" else f"+{free_reward[1]} olmos"
        premium_labels = {
            ("coins", 100): "+100 🪙",
            ("diamond", 1): "+1 💎",
            ("item", "vip_frame"): "👑 VIP ramka",
            ("item", "gold_badge"): "🥇 Oltin nishon",
            ("item", "premium_frame"): "💠 Premium ramka",
        }
        premium_label = premium_labels.get(premium_reward, "maxsus sovg‘a")
        free_state = "✅ olindi" if str(i) in free_claims else ("🎁 tayyor" if xp >= needed else "🔒")
        premium_state = "✅ olindi" if str(i) in premium_claims else ("🎁 tayyor" if xp >= needed else "🔒")
        lines.append(
            f"<b>#{i} · {needed} XP</b>\n"
            f"🟢 Free: {free_label} — {free_state}\n"
            f"💎 Premium: {premium_label} — {premium_state}"
        )
    free_status = "🟢 <b>OCHIQ</b>" if free_pass else f"🔒 <b>YOPIQ</b> · {_FREE_PASS_COST} 🪙"
    premium_status = "💎 <b>OCHIQ</b>" if premium_pass else f"🔒 <b>YOPIQ</b> · {_PREMIUM_PASS_STARS} ⭐"
    await message.answer(
        f"🎟️ <b>MAFIA UZ · BATTLE PASS</b>\n"
        f"<blockquote>Har bir o‘yin XP beradi. Darajalarni ochib, ikki yo‘nalishda sovg‘a yig‘ing!</blockquote>\n\n"
        f"📅 Mavsum: <code>{month}</code>\n"
        f"⭐ Sizning XP: <b>{xp}</b>\n"
        f"🪙 Balans: <b>{coins}</b>\n\n"
        f"🟢 <b>FREE PASS:</b> {free_status}\n"
        f"💎 <b>PREMIUM PASS:</b> {premium_status}\n\n"
        + "\n\n".join(lines)
        + "\n\n<i>Free Pass bir mavsum uchun tangaga ochiladi. Premium Pass 30 ⭐ turadi va VIP buyumlar beradi.</i>",
        reply_markup=_battlepass_keyboard(free_pass, premium_pass),
    )


@router.callback_query(F.data == "progress:bp:unlock_free")
async def battlepass_unlock_free(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    uid = callback.from_user.id
    month = _season()
    async with get_session_factory()() as session:
        async with session.begin():
            key = f"u:{uid}:bp_free:{month}"
            if await _value(session, key, "0") == "1":
                result = "Free Pass bu mavsumda allaqachon ochilgan."
            else:
                balance = int(await _value(session, f"u:{uid}:coins", "100"))
                if balance < _FREE_PASS_COST:
                    result = f"Free Pass uchun {_FREE_PASS_COST} 🪙 kerak. Sizda {balance} 🪙 bor."
                else:
                    await _set(session, f"u:{uid}:coins", str(balance - _FREE_PASS_COST))
                    await _set(session, key, "1")
                    result = "🟢 Free Pass ochildi! Endi XP bosqichlaridan tangalarni olishingiz mumkin."
    await callback.answer(result, show_alert=True)
@router.callback_query(F.data.startswith("progress:bp:"))
async def battlepass_claim(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or parts[2] not in {"free", "premium"}:
        await callback.answer("Battle Pass tugmasi noto‘g‘ri.", show_alert=True)
        return
    track = parts[2]
    try:
        tier_index = int(parts[3])
        tier = _BATTLEPASS_TIERS[tier_index - 1]
    except (ValueError, IndexError):
        await callback.answer("Battle Pass bosqichi noto‘g‘ri.", show_alert=True)
        return
    uid = callback.from_user.id
    month = _season()
    needed = tier["xp"]
    reward_type, reward_value = tier[track]
    async with get_session_factory()() as session:
        async with session.begin():
            user = await session.get(User, uid)
            if not user:
                await callback.answer("Avval /start buyrug‘ini yuboring.", show_alert=True)
                return
            pass_key = f"u:{uid}:bp_{track}:{month}"
            if await _value(session, pass_key, "0") != "1":
                result = "Avval shu passni oching."
            elif _xp(user) < needed:
                result = f"Bu mukofot uchun {needed} XP kerak."
            else:
                claims_key = f"u:{uid}:bp_{track}_claims:{month}"
                try:
                    claims = json.loads(await _value(session, claims_key, "[]"))
                except (TypeError, json.JSONDecodeError):
                    claims = []
                if str(tier_index) in claims:
                    result = "Bu mukofotni oldin olgansiz."
                else:
                    if reward_type == "coins":
                        balance = await _add_coins(session, uid, int(reward_value))
                        result = f"🎉 {track.title()} Pass mukofoti: +{reward_value} 🪙. Balans: {balance} 🪙"
                    elif reward_type == "diamond":
                        key = f"u:{uid}:diamonds"
                        diamonds = int(await _value(session, key, "0")) + int(reward_value)
                        await _set(session, key, str(diamonds))
                        result = f"💎 Premium Pass mukofoti: +{reward_value} olmos."
                    else:
                        item_key = f"u:{uid}:items"
                        try:
                            inventory = json.loads(await _value(session, item_key, "[]"))
                        except (TypeError, json.JSONDecodeError):
                            inventory = []
                        item_id = str(reward_value)
                        if item_id in inventory:
                            balance = await _add_coins(session, uid, 100)
                            result = f"Buyum sizda bor ekan — o‘rniga +100 🪙. Balans: {balance} 🪙"
                        else:
                            inventory.append(item_id)
                            await _set(session, item_key, json.dumps(inventory, ensure_ascii=False))
                            result = f"🎁 Premium Pass sovg‘asi olindi: <b>{item_id}</b>"
                    claims.append(str(tier_index))
                    await _set(session, claims_key, json.dumps(claims))
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
