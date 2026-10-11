import json
import random
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database import get_session_factory
from app.keyboards import main_menu_keyboard
from app.models import BotSetting, User
from app.services.rooms import register_user

router = Router(name="features")

SHOP_ITEMS = {
    "lucky_charm": {"name": "🍀 Omad tumor", "price": 50, "description": "Solo o‘yinda bir marta qo‘shimcha imkoniyat."},
    "detective_badge": {"name": "🕵️ Detektiv nishoni", "price": 100, "description": "Profilingiz uchun maxsus nishon."},
    "vip_frame": {"name": "👑 VIP ramka", "price": 250, "description": "Profilingiz uchun VIP bezak."},
    "gold_badge": {"name": "🥇 Oltin nishon", "price": 300, "description": "Profilingiz uchun noyob kolleksiya buyumi."},
    "neon_theme": {"name": "🌌 Neon mavzu", "price": 220, "description": "Profilingiz uchun neon uslubidagi kolleksiya."},
    "ghost_emote": {"name": "👻 Arvoh emojisi", "price": 120, "description": "Inventaringiz uchun maxsus emojili buyum."},
    "diamond_crown": {"name": "💎 Olmos toj", "price": 500, "description": "Shopdagi premium kolleksiya buyumi."},
}


async def _get_value(session, key: str, default: str) -> str:
    setting = await session.get(BotSetting, key)
    return setting.value if setting else default


async def _set_value(session, key: str, value: str) -> None:
    setting = await session.get(BotSetting, key)
    if setting is None:
        session.add(BotSetting(key=key, value=value))
    else:
        setting.value = value


async def _ensure_user(session, tg_user) -> User:
    name = " ".join(part for part in [tg_user.first_name, tg_user.last_name] if part).strip()
    return await register_user(session, tg_user.id, tg_user.username, name or tg_user.full_name)


async def _coins(session, user_id: int) -> int:
    return int(await _get_value(session, f"u:{user_id}:coins", "100"))


async def _inventory(session, user_id: int) -> list[str]:
    return json.loads(await _get_value(session, f"u:{user_id}:items", "[]"))


async def _show_profile(message: Message) -> None:
    if message.from_user is None:
        return
    async with get_session_factory()() as session:
        async with session.begin():
            user = await _ensure_user(session, message.from_user)
            coins = await _coins(session, user.telegram_id)
            inventory = await _inventory(session, user.telegram_id)
            games, wins, losses = user.games_played, user.wins, user.losses
            display_name = user.display_name
    win_rate = round(wins * 100 / games) if games else 0
    await message.answer(
        f"👤 <b>Profil</b>\n\n"
        f"Ism: {escape(display_name)}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"🎮 O‘yinlar: <b>{games}</b>\n"
        f"🏆 G‘alabalar: <b>{wins}</b>\n"
        f"💔 Mag‘lubiyatlar: <b>{losses}</b>\n"
        f"📈 G‘alaba foizi: <b>{win_rate}%</b>\n"
        f"🪙 Tangalar: <b>{coins}</b>\n"
        f"🎒 Buyumlar: {len(inventory)}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("profile"))
@router.message(F.text.in_({"👤 Profil", "👤 Profilim"}))
async def profile_handler(message: Message) -> None:
    await _show_profile(message)


@router.message(Command("leaderboard"))
@router.message(F.text == "🏆 Reyting")
async def leaderboard_handler(message: Message) -> None:
    async with get_session_factory()() as session:
        users = list((await session.scalars(
            select(User).where(User.games_played > 0).order_by(User.wins.desc(), User.games_played.desc()).limit(10)
        )).all())
    if not users:
        await message.answer("🏆 Reyting hozircha bo‘sh. Birinchi bo‘lib Solo Game o‘ynang!", reply_markup=main_menu_keyboard())
        return
    lines = []
    for i, user in enumerate(users, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
        lines.append(f"{medal} {escape(user.display_name)} — {user.wins} g‘alaba / {user.games_played} o‘yin")
    await message.answer("🏆 <b>TOP 10 reyting</b>\n\n" + "\n".join(lines), reply_markup=main_menu_keyboard())


def _settings_keyboard(language: str, notifications: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌐 Til: {'O‘zbekcha' if language == 'uz' else 'Русский'}", callback_data="settings:language")],
        [InlineKeyboardButton(text=f"🔔 Bildirishnomalar: {'Yoqilgan' if notifications else 'O‘chirilgan'}", callback_data="settings:notifications")],
    ])


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Sozlamalar")
async def settings_handler(message: Message) -> None:
    if message.from_user is None:
        return
    async with get_session_factory()() as session:
        language = await _get_value(session, f"u:{message.from_user.id}:lang", "uz")
        notifications = await _get_value(session, f"u:{message.from_user.id}:notify", "1") == "1"
    await message.answer("⚙️ <b>Sozlamalar</b>\n\nTil va bildirishnoma sozlamalarini shu yerdan o‘zgartiring.", reply_markup=_settings_keyboard(language, notifications))


@router.callback_query(F.data == "settings:language")
async def toggle_language(callback: CallbackQuery) -> None:
    async with get_session_factory()() as session:
        async with session.begin():
            key = f"u:{callback.from_user.id}:lang"
            old = await _get_value(session, key, "uz")
            new = "ru" if old == "uz" else "uz"
            await _set_value(session, key, new)
            notifications = await _get_value(session, f"u:{callback.from_user.id}:notify", "1") == "1"
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_settings_keyboard(new, notifications))
    await callback.answer("Til sozlamasi saqlandi.")


@router.callback_query(F.data == "settings:notifications")
async def toggle_notifications(callback: CallbackQuery) -> None:
    async with get_session_factory()() as session:
        async with session.begin():
            key = f"u:{callback.from_user.id}:notify"
            old = await _get_value(session, key, "1")
            new = "0" if old == "1" else "1"
            await _set_value(session, key, new)
            language = await _get_value(session, f"u:{callback.from_user.id}:lang", "uz")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_settings_keyboard(language, new == "1"))
    await callback.answer("Bildirishnoma sozlamasi saqlandi.")


def _shop_keyboard(coins: int, inventory: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for item_id, item in SHOP_ITEMS.items():
        owned = item_id in inventory
        label = f"{'✅' if owned else '🛒'} {item['name']} — {item['price']} 🪙"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"shop:buy:{item_id}" if not owned else "shop:owned")])
    rows.append([InlineKeyboardButton(text="🔄 Yangilash", callback_data="shop:refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("shop"))
@router.message(F.text == "🛒 Shop")
async def shop_handler(message: Message) -> None:
    if message.from_user is None:
        return
    async with get_session_factory()() as session:
        coins = await _coins(session, message.from_user.id)
        inventory = await _inventory(session, message.from_user.id)
    details = "\n".join(f"{item['name']} — {item['price']} 🪙\n   {item['description']}" for item in SHOP_ITEMS.values())
    await message.answer(f"🛒 <b>Shop</b>\nBalansingiz: <b>{coins} 🪙</b>\n\n{details}", reply_markup=_shop_keyboard(coins, inventory))


@router.callback_query(F.data.startswith("shop:buy:"))
async def shop_buy(callback: CallbackQuery) -> None:
    item_id = (callback.data or "").rsplit(":", 1)[-1]
    item = SHOP_ITEMS.get(item_id)
    if item is None:
        await callback.answer("Bu buyum topilmadi.", show_alert=True)
        return
    async with get_session_factory()() as session:
        async with session.begin():
            await _ensure_user(session, callback.from_user)
            coins = await _coins(session, callback.from_user.id)
            inventory = await _inventory(session, callback.from_user.id)
            if item_id in inventory:
                result = "Siz bu buyumni oldin olgansiz."
            elif coins < item["price"]:
                result = "Tangalar yetarli emas. Solo Game o‘ynab tanga yig‘ing."
            else:
                inventory.append(item_id)
                await _set_value(session, f"u:{callback.from_user.id}:coins", str(coins - item["price"]))
                await _set_value(session, f"u:{callback.from_user.id}:items", json.dumps(inventory))
                coins -= item["price"]
                result = f"{item['name']} sotib olindi!"
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_shop_keyboard(coins, inventory))
    await callback.answer(result, show_alert=True)


@router.callback_query(F.data == "shop:refresh")
async def shop_refresh(callback: CallbackQuery) -> None:
    async with get_session_factory()() as session:
        coins = await _coins(session, callback.from_user.id)
        inventory = await _inventory(session, callback.from_user.id)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_shop_keyboard(coins, inventory))
    await callback.answer("Shop yangilandi.")


@router.callback_query(F.data == "shop:owned")
async def shop_owned(callback: CallbackQuery) -> None:
    await callback.answer("Bu buyum sizda bor.")


def _solo_keyboard(game: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗳️ {bot['name']}ni ayblash", callback_data=f"solo:vote:{i}") ]
        for i, bot in enumerate(game["bots"]) if bot["alive"]
    ])


@router.message(Command("solo"))
@router.message(F.text == "🤖 Solo Game")
async def solo_start(message: Message) -> None:
    if message.from_user is None:
        return
    names = ["Ali", "Madina", "Jasur", "Malika", "Bekzod", "Dilnoza"]
    random.shuffle(names)
    bots = [{"name": names[i], "role": "mafia" if i == 0 else ("doctor" if i == 1 else "citizen"), "alive": True} for i in range(4)]
    random.shuffle(bots)
    game = {"bots": bots, "round": 1, "status": "active"}
    async with get_session_factory()() as session:
        async with session.begin():
            await _ensure_user(session, message.from_user)
            await _set_value(session, f"u:{message.from_user.id}:solo", json.dumps(game))
    await message.answer(
        "🤖 <b>Solo Game boshlandi!</b>\n\n"
        "Siz — 🕵️ <b>Detektiv</b>. 4 ta AI bot orasida 1 ta mafiya bor.\n"
        "Botlardan birini tanlab, kim mafiya ekanini toping. To‘g‘ri topsangiz +50 🪙, aks holda o‘yin tugaydi.",
        reply_markup=_solo_keyboard(game),
    )


@router.callback_query(F.data.startswith("solo:vote:"))
async def solo_vote(callback: CallbackQuery) -> None:
    try:
        index = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Tanlov noto‘g‘ri.", show_alert=True)
        return
    async with get_session_factory()() as session:
        async with session.begin():
            user = await session.get(User, callback.from_user.id)
            raw = await _get_value(session, f"u:{callback.from_user.id}:solo", "")
            if user is None or not raw:
                await callback.answer("Avval yangi Solo Game boshlang.", show_alert=True)
                return
            game = json.loads(raw)
            if game.get("status") != "active" or index not in range(len(game["bots"])) or not game["bots"][index]["alive"]:
                await callback.answer("Bu o‘yin tugagan yoki tanlov yaroqsiz.", show_alert=True)
                return
            chosen = game["bots"][index]
            user.games_played += 1
            if chosen["role"] == "mafia":
                user.wins += 1
                coins = await _coins(session, user.telegram_id) + 50
                await _set_value(session, f"u:{user.telegram_id}:coins", str(coins))
                game["status"] = "won"
                result = f"🎉 To‘g‘ri! {chosen['name']} mafiya edi. Siz yutdingiz va +50 🪙 oldingiz."
            else:
                user.losses += 1
                game["status"] = "lost"
                mafia = next(bot for bot in game["bots"] if bot["role"] == "mafia")
                result = f"😵 Noto‘g‘ri! {chosen['name']} {chosen['role']} edi. Mafi ya {mafia['name']} bo‘lgan."
            await _set_value(session, f"u:{user.telegram_id}:solo", json.dumps(game))
    if callback.message:
        await callback.message.edit_text(result + "\n\nYana o‘ynash uchun 🤖 Solo Game tugmasini bosing.", reply_markup=None)
    await callback.answer("Natija tayyor.")
