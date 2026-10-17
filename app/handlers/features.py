import asyncio
import json
import random
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database import get_session_factory
from app.keyboards import main_menu_keyboard
from app.models import BotSetting, User
from app.progression import record_match_progress
from app.services.rooms import register_user

router = Router(name="features")

SHOP_ITEMS = {
    "lucky_charm": {"name": "🍀 Omad tumor", "price": 50, "description": "Solo o‘yinda bir marta o‘lim zarbasini qaytaradi; ishlatilgach inventardan ketadi."},
    "detective_badge": {"name": "🕵️ Detektiv nishoni", "price": 100, "description": "Profilingizda ko‘rinadigan detektiv nishoni."},
    "vip_frame": {"name": "👑 VIP ramka", "price": 250, "description": "Profilingizda ko‘rinadigan VIP bezagi."},
    "gold_badge": {"name": "🥇 Oltin nishon", "price": 300, "description": "Profilingizda ko‘rinadigan oltin nishon."},
    "neon_theme": {"name": "🌌 Neon mavzu", "price": 220, "description": "Profilingizda ko‘rinadigan neon uslubi."},
    "ghost_emote": {"name": "👻 Arvoh emojisi", "price": 120, "description": "Profilingizda ko‘rinadigan arvoh emojisi."},
    "diamond_crown": {"name": "💎 Olmos toj", "price": 2, "currency": "diamonds", "description": "2 olmos evaziga profil bezagi."},
    "premium_frame": {"name": "👑 Premium ramka", "price": 3, "currency": "diamonds", "description": "3 olmos evaziga maxsus profil ramkasi."},
    "premium_title": {"name": "💠 Afsonaviy unvon", "price": 700, "pass_required": True, "description": "Premium Pass egalariga maxsus profil unvoni; tangaga olinadi."},
    "mafia_aura": {"name": "🌌 Mafia aurasi", "price": 1200, "pass_required": True, "description": "Premium Pass egalariga noyob profil bezagi; tangaga olinadi."},
    "legendary_emote": {"name": "🔥 Afsonaviy emote", "price": 900, "pass_required": True, "description": "Premium Pass egalariga maxsus emote; tangaga olinadi."},
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


async def _premium_active(session, user_id: int) -> bool:
    raw = await _get_value(session, f"u:{user_id}:premium_until", "")
    if not raw:
        return False
    try:
        until = datetime.fromisoformat(raw)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > datetime.now(timezone.utc)
    except ValueError:
        return False


async def _show_profile(message: Message) -> None:
    if message.from_user is None:
        return
    async with get_session_factory()() as session:
        async with session.begin():
            user = await _ensure_user(session, message.from_user)
            coins = await _coins(session, user.telegram_id)
            diamonds = int(await _get_value(session, f"u:{user.telegram_id}:diamonds", "0"))
            inventory = await _inventory(session, user.telegram_id)
            premium_until = await _get_value(session, f"u:{user.telegram_id}:premium_until", "")
            games, wins, losses = user.games_played, user.wins, user.losses
            display_name = user.display_name
    premium_active = False
    premium_label = "Faol emas"
    if premium_until:
        try:
            parsed_until = datetime.fromisoformat(premium_until)
            if parsed_until.tzinfo is None:
                parsed_until = parsed_until.replace(tzinfo=timezone.utc)
            premium_active = parsed_until > datetime.now(timezone.utc)
            if premium_active:
                premium_label = f"Faol · {parsed_until.strftime('%Y-%m-%d')} gacha"
        except ValueError:
            pass
    win_rate = round(wins * 100 / games) if games else 0
    xp = games * 10 + wins * 25
    level = xp // 100 + 1
    current_level_xp = xp % 100
    progress_blocks = current_level_xp // 10
    progress_bar = "🟩" * progress_blocks + "⬜" * (10 - progress_blocks)
    achievements = []
    if games >= 1: achievements.append("🎮 Birinchi o‘yin")
    if wins >= 1: achievements.append("🏆 Birinchi g‘alaba")
    if wins >= 10: achievements.append("🔥 10 g‘alaba")
    if games >= 25: achievements.append("🎖️ Tajribali o‘yinchi")
    await message.answer(
        f"👤 <b>MAFIA UZ · PROFIL</b>\n"
        f"<blockquote>Strategiyangni ko‘rsat. Har bir o‘yin seni kuchaytiradi.</blockquote>\n\n"
        f"Ism: {escape(display_name)}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"🎮 O‘yinlar: <b>{games}</b>\n"
        f"🏆 G‘alabalar: <b>{wins}</b>\n"
        f"💔 Mag‘lubiyatlar: <b>{losses}</b>\n"
        f"📈 G‘alaba foizi: <b>{win_rate}%</b>\n"
        f"⭐ XP: <b>{xp}</b> · 🎖️ Daraja: <b>{level}</b>\n"
        f"{progress_bar} <code>{current_level_xp}/100 XP</code>\n"
        f"🏅 Yutuqlar: {', '.join(achievements) if achievements else 'Hali yo‘q — birinchi o‘yinni boshlang!'}\n"
        f"🪙 Tangalar: <b>{coins}</b>\n"
        f"💎 Olmoslar: <b>{diamonds}</b>\n"
        f"👑 Premium: <b>{escape(premium_label)}</b>\n"
        f"🎒 Buyumlar ({len(inventory)}): " + (", ".join(SHOP_ITEMS[item_id]["name"] for item_id in inventory if item_id in SHOP_ITEMS) or "hali yo‘q"),
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


def _shop_keyboard(coins: int, diamonds: int, inventory: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for item_id, item in SHOP_ITEMS.items():
        owned = item_id in inventory
        currency_icon = "💎" if item.get("currency") == "diamonds" else "🪙"
        pass_icon = " 💎" if item.get("pass_required") else ""
        label = f"{'✅' if owned else '🛒'} {item['name']} — {item['price']} {currency_icon}{pass_icon}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"shop:buy:{item_id}" if not owned else "shop:owned")])
    rows.extend([
        [InlineKeyboardButton(text="🎁 Oddiy sandiq — 100 🪙", callback_data="shop:crate:choose:basic")],
        [InlineKeyboardButton(text="💎 Premium sandiq — 250 🪙", callback_data="shop:crate:choose:premium")],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="shop:refresh")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("shop"))
@router.message(F.text == "🛒 Shop")
async def shop_handler(message: Message) -> None:
    if message.from_user is None:
        return
    async with get_session_factory()() as session:
        coins = await _coins(session, message.from_user.id)
        diamonds = int(await _get_value(session, f"u:{message.from_user.id}:diamonds", "0"))
        inventory = await _inventory(session, message.from_user.id)
    details = "\n".join(
        f"{item['name']} — {item['price']} {'💎' if item.get('currency') == 'diamonds' else '🪙'}\n   {item['description']}"
        for item in SHOP_ITEMS.values()
    )
    await message.answer(
        f"🛒 <b>MAFIA SHOP</b>\nBalans: <b>{coins} 🪙</b> · <b>{diamonds} 💎</b>\n\n{details}",
        reply_markup=_shop_keyboard(coins, diamonds, inventory),
    )


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
            diamonds = int(await _get_value(session, f"u:{callback.from_user.id}:diamonds", "0"))
            inventory = await _inventory(session, callback.from_user.id)
            currency = item.get("currency", "coins")
            if item.get("pass_required"):
                month = datetime.now(timezone.utc).strftime("%Y-%m")
                if await _get_value(session, f"u:{callback.from_user.id}:bp_premium:{month}", "0") != "1":
                    result = "💎 Bu buyumlar faqat Premium Pass egalariga ochiq. /battlepass orqali 30 ⭐ ga oling."
                    balance = coins
                else:
                    balance = diamonds if currency == "diamonds" else coins
            else:
                balance = diamonds if currency == "diamonds" else coins
            currency_key = f"u:{callback.from_user.id}:diamonds" if currency == "diamonds" else f"u:{callback.from_user.id}:coins"
            if item.get("pass_required") and await _get_value(session, f"u:{callback.from_user.id}:bp_premium:{datetime.now(timezone.utc).strftime('%Y-%m')}", "0") != "1":
                result = "💎 Bu buyumlar faqat Premium Pass egalariga ochiq. /battlepass orqali 30 ⭐ ga oling."
            elif item_id in inventory:
                result = "Siz bu buyumni oldin olgansiz."
            elif balance < item["price"]:
                result = "Olmos yetarli emas." if currency == "diamonds" else "Tangalar yetarli emas. Solo Game o‘ynab tanga yig‘ing."
            else:
                inventory.append(item_id)
                await _set_value(session, currency_key, str(balance - item["price"]))
                await _set_value(session, f"u:{callback.from_user.id}:items", json.dumps(inventory, ensure_ascii=False))
                if currency == "diamonds":
                    diamonds -= item["price"]
                else:
                    coins -= item["price"]
                result = f"{item['name']} sotib olindi!"
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_shop_keyboard(coins, diamonds, inventory))
    await callback.answer(result, show_alert=True)


@router.callback_query(F.data == "shop:refresh")
async def shop_refresh(callback: CallbackQuery) -> None:
    async with get_session_factory()() as session:
        coins = await _coins(session, callback.from_user.id)
        diamonds = int(await _get_value(session, f"u:{callback.from_user.id}:diamonds", "0"))
        inventory = await _inventory(session, callback.from_user.id)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_shop_keyboard(coins, diamonds, inventory))
    await callback.answer("Shop yangilandi.")


@router.callback_query(F.data == "shop:owned")
async def shop_owned(callback: CallbackQuery) -> None:
    await callback.answer("Bu buyum sizda bor.")


@router.callback_query(F.data.startswith("shop:crate:choose:"))
async def choose_crate_quantity(callback: CallbackQuery) -> None:
    crate = (callback.data or "").rsplit(":", 1)[-1]
    if crate not in {"basic", "premium"}:
        await callback.answer("Sandiq turi topilmadi.", show_alert=True)
        return
    price = 100 if crate == "basic" else 250
    label = "Oddiy" if crate == "basic" else "Premium"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1 ta · {price} 🪙", callback_data=f"shop:crate:open:{crate}:1")],
        [InlineKeyboardButton(text=f"3 ta · {price*3} 🪙", callback_data=f"shop:crate:open:{crate}:3")],
        [InlineKeyboardButton(text=f"5 ta · {price*5} 🪙", callback_data=f"shop:crate:open:{crate}:5")],
        [InlineKeyboardButton(text="⬅️ Shopga qaytish", callback_data="shop:refresh")],
    ])
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"🎁 <b>{label} sandiq</b>\n\nNechta ochmoqchisiz?\n"
            "Balansingiz yetarli bo‘lsa, tanlangan sandiqlar ochiladi. Yetmasa, tanga yechilmaydi.",
            reply_markup=keyboard,
        )


@router.callback_query(F.data.startswith("shop:crate:"))
async def shop_open_crate(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) == 3:
        crate, quantity = parts[2], 1
    elif len(parts) == 5 and parts[2] == "open":
        crate = parts[3]
        try:
            quantity = int(parts[4])
        except ValueError:
            quantity = 0
    else:
        await callback.answer("Sandiq tanlovi noto‘g‘ri.", show_alert=True)
        return
    if crate not in {"basic", "premium"} or quantity not in {1, 3, 5}:
        await callback.answer("Sandiq miqdori noto‘g‘ri.", show_alert=True)
        return
    uid = callback.from_user.id
    cost_each = 100 if crate == "basic" else 250
    total_cost = cost_each * quantity
    rewards: dict[str, int] = {}
    new_items: list[str] = []
    async with get_session_factory()() as session:
        async with session.begin():
            await _ensure_user(session, callback.from_user)
            balance = await _coins(session, uid)
            if balance < total_cost:
                result = f"❌ Tanga yetarli emas. {quantity} ta sandiq uchun {total_cost} 🪙 kerak, balansingizda {balance} 🪙 bor. Hech narsa yechilmadi."
            else:
                await _set_value(session, f"u:{uid}:coins", str(balance - total_cost))
                inventory = await _inventory(session, uid)
                if crate == "basic":
                    drops = [
                        ("coins", 50, 40), ("coins", 100, 30),
                        ("item", "detective_badge", 15), ("item", "ghost_emote", 10),
                        ("diamond", 1, 5),
                    ]
                else:
                    drops = [
                        ("coins", 100, 25), ("coins", 250, 25),
                        ("item", "vip_frame", 20), ("item", "gold_badge", 15),
                        ("diamond", 1, 10), ("diamond", 2, 5),
                    ]
                for _ in range(quantity):
                    kind, reward, _weight = random.choices(drops, weights=[entry[2] for entry in drops], k=1)[0]
                    if kind == "coins":
                        rewards["🪙 tanga"] = rewards.get("🪙 tanga", 0) + int(reward)
                    elif kind == "diamond":
                        rewards["💎 olmos"] = rewards.get("💎 olmos", 0) + int(reward)
                    else:
                        item_id = str(reward)
                        item = SHOP_ITEMS[item_id]
                        if item_id in inventory:
                            rewards["🪙 tanga (takroriy buyum o‘rniga)"] = rewards.get("🪙 tanga (takroriy buyum o‘rniga)", 0) + 75
                        else:
                            inventory.append(item_id)
                            new_items.append(item["name"])
                current_coins = await _coins(session, uid)
                current_diamonds = int(await _get_value(session, f"u:{uid}:diamonds", "0"))
                current_coins += rewards.get("🪙 tanga", 0) + rewards.get("🪙 tanga (takroriy buyum o‘rniga)", 0)
                current_diamonds += rewards.get("💎 olmos", 0)
                await _set_value(session, f"u:{uid}:coins", str(current_coins))
                await _set_value(session, f"u:{uid}:diamonds", str(current_diamonds))
                await _set_value(session, f"u:{uid}:items", json.dumps(inventory, ensure_ascii=False))
                summary = [f"• {label}: <b>+{amount}</b>" for label, amount in rewards.items()]
                summary.extend(f"• 🎁 {escape(name)}" for name in new_items)
                result = (
                    f"🎉 <b>{quantity} ta sandiq ochildi!</b>\n"
                    f"🪙 Sarflandi: <b>{total_cost} tanga</b>\n\n"
                    + ("\n".join(summary) if summary else "Bu safar buyum chiqmagan.")
                    + f"\n\n💰 Yangi balans: <b>{current_coins} 🪙</b> · <b>{current_diamonds} 💎</b>"
                )
    await callback.answer("Sandiqlar ochildi." if "🎉" in result else "Tanga yetarli emas.", show_alert=True)
    if callback.message:
        await callback.message.answer(result)
        try:
            async with get_session_factory()() as session:
                coins = await _coins(session, uid)
                diamonds = int(await _get_value(session, f"u:{uid}:diamonds", "0"))
                inventory = await _inventory(session, uid)
            await callback.message.edit_reply_markup(reply_markup=_shop_keyboard(coins, diamonds, inventory))
        except Exception:
            pass


SOLO_NAMES = ["Ali", "Madina", "Jasur", "Malika", "Bekzod", "Dilnoza", "Sardor", "Zarina", "Aziz", "Mohira", "Kamron", "Sevara", "Diyor", "Nodira", "Rustam", "Shahnoza"]
SOLO_ROLE_INFO = {
    "mafia": ("🔪", "Mafiya", "Har tun bir tirik o‘yinchini yo‘q qilishga urinadi."),
    "don": ("🕴️", "Don", "Mafiya yetakchisi. Har tun hujum qiladi va tekshiruvda oddiy fuqaro bo‘lib ko‘rinadi."),
    "doctor": ("🩺", "Shifokor", "Har tun bir o‘yinchini, jumladan o‘zingizni, himoya qilishingiz mumkin."),
    "detective": ("🕵️", "Detektiv", "Har tun bir o‘yinchini tekshirib, u mafiya jamoasida ekanini bilib olasiz."),
    "bodyguard": ("🛡️", "Tansoqchi", "Har tun bir o‘yinchini himoya qilasiz. Hujum unga tegsa, siz zararni qabul qilishingiz mumkin."),
    "maniac": ("🪓", "Manyak", "Yolg‘iz o‘ynaydi va har tun bitta nishonni yo‘q qilishga urinadi."),
    "citizen": ("👤", "Fuqaro", "Maxsus tungi kuch yo‘q. Kuzatish va ovoz bilan shaharni qutqaring."),
}
# Direct, lightweight GIPHY renditions instead of the old unverified media IDs.
SOLO_GIF = {
    # Direct GIF renditions for Mafia intro, night atmosphere, investigation and victory.
    "intro": "https://media.giphy.com/media/ze5DIMqmLOKpg2yVlK/giphy.gif",
    "night": "https://media.giphy.com/media/5xtDarISMPAiPgViP60/giphy.gif",
    "vote": "https://media.giphy.com/media/NxXXk9WRK18wjmTOyZ/giphy.gif",
    "win": "https://media.giphy.com/media/UrAt4W0jlp1Ksir8ls/giphy.gif",
}


def _solo_setup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 5 kishi", callback_data="solo:setup:5"),
         InlineKeyboardButton(text="👥 7 kishi", callback_data="solo:setup:7"),
         InlineKeyboardButton(text="👥 9 kishi", callback_data="solo:setup:9")],
        [InlineKeyboardButton(text="👥 12 kishi", callback_data="solo:setup:12"),
         InlineKeyboardButton(text="👥 15 kishi", callback_data="solo:setup:15")],
    ])


def _solo_role_plan(total: int) -> list[str]:
    # Total includes the human player. Role composition scales with table size.
    roles = ["don", "doctor", "detective", "bodyguard"]
    if total >= 7:
        roles += ["maniac"]
    if total >= 9:
        roles += ["mafia"]
    if total >= 12:
        roles += ["mafia"]
    roles += ["citizen"] * max(0, total - len(roles))
    return roles[:total]


def _solo_keyboard(game: dict, mode: str = "vote") -> InlineKeyboardMarkup:
    human = next((p for p in game["bots"] if p.get("is_player")), None)
    if human and not human.get("alive", True):
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✍️ Oxirgi so‘z", callback_data="solo:spectator:lastwords"),
                InlineKeyboardButton(text="🚪 Kuzatuvdan chiqish", callback_data="solo:spectator:exit"),
            ]
        ])
    rows = []
    for i, bot in enumerate(game["bots"]):
        if not bot["alive"]:
            continue
        if bot.get("is_player") and mode != "vote" and not (
            mode == "night" and game.get("player_role") in {"doctor", "bodyguard"}
        ):
            continue
        label = "🧑 Siz (o‘zingiz)" if bot.get("is_player") else f"{bot['emoji']} {bot['name']}"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"solo:{mode}:{i}",
        )])
    if game.get("phase") == "night" and game.get("player_role") in {"doctor", "bodyguard"}:
        rows.append([InlineKeyboardButton(text="⏭️ Himoya qilmaslik", callback_data="solo:skip:0")])
    if game.get("phase") == "night" and game.get("player_role") == "citizen":
        rows.append([InlineKeyboardButton(text="🌙 Tunni davom ettirish", callback_data="solo:continue")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _solo_alive(game: dict) -> list[dict]:
    return [p for p in game["bots"] if p["alive"]]


def _solo_team(role: str) -> str:
    if role in {"mafia", "don"}:
        return "mafia"
    if role == "maniac":
        return "maniac"
    return "town"


def _solo_winner(game: dict) -> str | None:
    alive = _solo_alive(game)
    mafia = sum(_solo_team(p["role"]) == "mafia" for p in alive)
    maniac = sum(p["role"] == "maniac" for p in alive)
    town = len(alive) - mafia - maniac
    if mafia == 0 and maniac == 0:
        return "town"
    if maniac and maniac >= mafia + town:
        return "maniac"
    if mafia and mafia >= town + maniac:
        return "mafia"
    return None


def _solo_finish(game: dict, winner: str) -> None:
    game["status"] = "finished"
    game["phase"] = "finished"
    game["winner"] = winner



def _solo_autoplay_after_elimination(game: dict) -> str:
    """Continue the bot-only match after the human player is eliminated."""
    human = next((p for p in game["bots"] if p.get("is_player")), None)
    role_text = _solo_role_label(human["role"]) if human else "noma’lum rol"
    narration = [
        f"🕯️ Siz o‘yindan chiqdingiz. Sizning rolingiz: <b>{role_text}</b>.",
        "👁️ Qolgan o‘yinchilar o‘yinni avtomatik davom ettiradi. Oxirgi so‘zingizni aytishingiz yoki kuzatuvdan chiqishingiz mumkin."
    ]
    for _ in range(40):
        alive = _solo_alive(game)
        winner = _solo_winner(game)
        if winner:
            _solo_finish(game, winner)
            break
        if len(alive) <= 1:
            _solo_finish(game, "draw")
            break

        # Night: mafia and maniac attack; doctor/bodyguard may protect one target.
        attacks = []
        mafia = [p for p in alive if p["role"] in {"mafia", "don"}]
        mafia_targets = [p for p in alive if _solo_team(p["role"]) != "mafia"]
        if mafia and mafia_targets:
            attacks.append((random.choice(mafia_targets), "mafia"))
        maniacs = [p for p in alive if p["role"] == "maniac"]
        maniac_targets = [p for p in alive if p["role"] != "maniac"]
        if maniacs and maniac_targets:
            attacks.append((random.choice(maniac_targets), "maniac"))
        protectors = [p for p in alive if p["role"] in {"doctor", "bodyguard"}]
        protected = random.choice(alive) if protectors and random.random() < 0.65 else None
        killed = set()
        for target, source in attacks:
            if protected and target["id"] == protected["id"]:
                narration.append(f"🛡️ {target['name']} hujumdan qutuldi.")
            elif target["id"] not in killed:
                target["alive"] = False
                killed.add(target["id"])
                narration.append(f"🌙 {target['name']} ({_solo_role_label(target['role'])}) tunda chiqib ketdi.")

        winner = _solo_winner(game)
        if winner:
            _solo_finish(game, winner)
            break

        # Day vote among surviving bots: show each voter's name and choice.
        alive = _solo_alive(game)
        tally = {p["id"]: 0 for p in alive}
        narration.append(f"☀️ {game.get('round', 1)}-kun: muhokama boshlandi.")
        for voter in alive:
            choices = [p for p in alive if p["id"] != voter["id"]]
            if not choices:
                continue
            if _solo_team(voter["role"]) == "mafia":
                preferred = [p for p in choices if _solo_team(p["role"]) != "mafia"]
            elif voter["role"] == "maniac":
                preferred = [p for p in choices if p["role"] != "maniac"]
            else:
                preferred = [p for p in choices if _solo_team(p["role"]) == "mafia"]
            pool = preferred if preferred and random.random() < 0.7 else choices
            vote_target = random.choice(pool)
            tally[vote_target["id"]] += 1
            comment = random.choice([
                f"{vote_target['name']}ning harakati menga shubhali.",
                f"Men {vote_target['name']}ga ovoz beraman.",
                f"{vote_target['name']}dan izoh kutyapman.",
                f"Hozircha {vote_target['name']}ni tanlayman.",
            ])
            narration.append(f"🗳️ <b>{voter['name']}</b>: {comment} Ovoz → <b>{vote_target['name']}</b>")
        if random.random() < 0.28 and len(alive) > 1:
            giver, receiver = random.sample(alive, 2)
            gift = random.choice(["🌹 atirgul", "🍫 shokolad", "☕ qahva", "🎁 kichik sovg‘a"])
            narration.append(f"🎁 <b>{giver['name']}</b> {receiver['name']}ga {gift} yubordi.")
        if tally:
            high = max(tally.values())
            leaders = [p for p in alive if tally[p["id"]] == high]
            if len(leaders) == 1 and random.random() < 0.82:
                nominee = leaders[0]
                nominee["alive"] = False
                narration.append(f"⚖️ Ovoz natijasi: {nominee['name']} ({_solo_role_label(nominee['role'])}) o‘yindan chiqarildi.")
            else:
                narration.append("🤝 Ovozlar tenglashdi, hech kim chiqarilmadi.")

        winner = _solo_winner(game)
        if winner:
            _solo_finish(game, winner)
            break
        game["round"] = int(game.get("round", 1)) + 1
    if game.get("status") != "finished":
        _solo_finish(game, "draw")
    winner = game.get("winner", "draw")
    narration.append({
        "town": "🏙️ Shahar g‘alaba qozondi!",
        "mafia": "🔪 Mafiya g‘alaba qozondi!",
        "maniac": "🪓 Manyak g‘alaba qozondi!",
        "draw": "🤝 O‘yin durang bilan tugadi.",
    }.get(winner, "O‘yin tugadi."))
    game["spectator_log"] = narration
    return "\n".join(narration)


def _solo_role_label(role: str):
    emoji, name, _ = SOLO_ROLE_INFO[role]
    return f"{emoji} {name}"


def _solo_assign_roles(total: int, player_id: int) -> tuple[list[dict], str]:
    roles = _solo_role_plan(total)
    random.shuffle(roles)
    player_role = roles.pop()
    people = [{"id": player_id, "name": "Siz", "role": player_role, "alive": True,
               "is_player": True, "emoji": "🧑"}]
    names = SOLO_NAMES.copy()
    random.shuffle(names)
    for i, role in enumerate(roles):
        people.append({"id": -(i + 1), "name": names[i], "role": role, "alive": True,
                       "is_player": False, "emoji": SOLO_ROLE_INFO[role][0]})
    return people, player_role


async def _solo_advance_night(game: dict) -> str:
    """Resolve AI actions for the night and return a short narrative."""
    alive = _solo_alive(game)
    messages = []
    protectors = [p for p in alive if p["role"] in {"doctor", "bodyguard"}]
    mafia = [p for p in alive if p["role"] in {"mafia", "don"}]
    maniacs = [p for p in alive if p["role"] == "maniac"]
    targets = [p for p in alive if p["role"] not in {"mafia", "don"}]
    attacks = []
    if mafia and targets:
        attacks.append((random.choice(targets), "mafia"))
    if maniacs:
        targets = [p for p in alive if p["role"] != "maniac"]
        if targets:
            attacks.append((random.choice(targets), "maniac"))
    protected = []
    for protector in protectors:
        choices = [p for p in alive if p["id"] != protector["id"]]
        if choices and random.random() < 0.8:
            protected.append(random.choice(choices))
    for target, source in attacks:
        if any(p["id"] == target["id"] for p in protected):
            messages.append(f"🛡️ {target['name']}ga qilingan hujum qaytarildi.")
            continue
        target["alive"] = False
        messages.append(f"💀 {target['name']} tunda halok bo‘ldi.")
    if not messages:
        messages.append("🌅 Tun tinch o‘tdi — hech kim halok bo‘lmadi.")
    return "\n".join(messages)


@router.message(Command("solo"))
@router.message(F.text == "🤖 Solo Game")
async def solo_start(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer(
        "🎭 <b>MAFIA: SOLO CAMPAIGN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>Yolg‘on, kuzatuv va strategiya — har bir qaroringiz muhim.</blockquote>\n"
        "👥 Stol atrofidagi jami o‘yinchilar sonini tanlang. Siz ham shu songa kiradi.\n\n"
        "🎲 <b>Rollar:</b> mafiya, Don, shifokor, detektiv, tansoqchi, manyak yoki fuqaro.\n"
        "🌙 <b>Tun</b> → ☀️ <i>muhokama</i> → 🗳️ <b>ovoz</b> → ⚖️ <b>sud</b> → 🏁 <b>g‘alaba</b>.\n\n"
        "✨ <i>Matnlar qalin, kursiv, iqtibos va belgilar bilan bezatilgan.</i>",
        reply_markup=_solo_setup_keyboard(),
    )


@router.callback_query(F.data.startswith("solo:setup:"))
async def solo_setup(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    try:
        total = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("O‘yinchi soni noto‘g‘ri.", show_alert=True)
        return
    if total not in {5, 7, 9, 12, 15}:
        await callback.answer("Mavjud o‘yinchi sonidan tanlang.", show_alert=True)
        return
    players, player_role = _solo_assign_roles(total, callback.from_user.id)
    game = {
        "total": total, "bots": players, "player_role": player_role,
        "round": 1, "status": "active", "phase": "night", "night_action": None,
        "last_protected": None, "last_inspected": None, "log": [],
    }
    async with get_session_factory()() as session:
        async with session.begin():
            await _ensure_user(session, callback.from_user)
            await _set_value(session, f"u:{callback.from_user.id}:solo", json.dumps(game, ensure_ascii=False))
    emoji, role_name, role_desc = SOLO_ROLE_INFO[player_role]
    text = (
        "🎬 <b>MAFIA — O‘YIN BOSHLANDI</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 Ishtirokchilar: <b>{total}</b>\n"
        f"🌙 Raund: <b>1</b> · <b>TUN</b>\n\n"
        f"🎭 <b>Sizning maxfiy rolingiz: {emoji} {role_name}</b>\n"
        f"📜 {role_desc}\n\n"
        "🤫 Rolingizni sir saqlang. Har bir qaror keyingi bosqichga ta’sir qiladi."
    )
    if player_role in {"mafia", "don"}:
        teammates = [p["name"] for p in players if _solo_team(p["role"]) == "mafia" and not p.get("is_player")]
        text += "\n\n🤝 <b>Mafiya jamoasi:</b> " + (", ".join(teammates) or "Siz yagona mafiya vakilisiz.")
    if callback.message:
        try:
            await callback.message.answer_animation(
                animation=SOLO_GIF["intro"], caption=text,
                reply_markup=_solo_keyboard(game, "night"),
            )
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            try:
                await callback.message.edit_text(text, reply_markup=_solo_keyboard(game, "night"))
            except Exception:
                await callback.message.answer(text, reply_markup=_solo_keyboard(game, "night"))
    await callback.answer("O‘yin yaratildi!")


@router.callback_query(F.data.startswith("solo:skip:"))
async def solo_skip(callback: CallbackQuery) -> None:
    await _solo_process_night(callback, None)


@router.callback_query(F.data == "solo:continue")
async def solo_continue(callback: CallbackQuery) -> None:
    await _solo_process_night(callback, None)


@router.callback_query(F.data.startswith("solo:night:"))
async def solo_night(callback: CallbackQuery) -> None:
    try:
        target_index = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Nishon noto‘g‘ri.", show_alert=True)
        return
    await _solo_process_night(callback, target_index)


async def _solo_process_night(callback: CallbackQuery, target_index: int | None) -> None:
    uid = callback.from_user.id
    result_text = ""
    game = None
    spectator_messages: list[str] = []
    async with get_session_factory()() as session:
        async with session.begin():
            raw = await _get_value(session, f"u:{uid}:solo", "")
            if not raw:
                await callback.answer("Avval yangi Solo Game boshlang.", show_alert=True)
                return
            game = json.loads(raw)
            if game.get("status") != "active" or game.get("phase") != "night":
                await callback.answer("Hozir tun bosqichi emas.", show_alert=True)
                return
            player = next((p for p in game["bots"] if p.get("is_player")), None)
            if not player or not player["alive"]:
                await callback.answer("Siz o‘yindan chiqib ketgansiz.", show_alert=True)
                return
            role = player["role"]
            target = game["bots"][target_index] if target_index is not None and 0 <= target_index < len(game["bots"]) else None
            if target_index is not None and (
                target is None or not target["alive"]
                or (target.get("is_player") and role not in {"doctor", "bodyguard"})
            ):
                await callback.answer("Bu nishonni tanlab bo‘lmaydi.", show_alert=True)
                return
            if role in {"mafia", "don", "maniac"} and target is None:
                await callback.answer("Hujum uchun nishon tanlang.", show_alert=True)
                return
            if role in {"doctor", "bodyguard"} and target is None:
                game["night_action"] = {"type": role, "target": None}
            elif role in {"mafia", "don"} and _solo_team(target["role"]) == "mafia":
                await callback.answer("O‘z jamoangizga hujum qila olmaysiz.", show_alert=True)
                return
            else:
                if role == "detective" and target and game.get("last_inspected") == target["id"]:
                    await callback.answer("O‘tgan tunda shu odamni tekshirgansiz. Boshqasini tanlang.", show_alert=True)
                    return
                game["night_action"] = {"type": role, "target": target["id"] if target else None}
                if role == "detective" and target:
                    game["last_inspected"] = target["id"]
                    truth = "mafiya jamoasida" if _solo_team(target["role"]) == "mafia" else "mafiya emas"
                    result_text = f"🕵️ <b>Maxfiy tekshiruv</b>\n{target['name']} — <b>{truth}</b>."
            # Simulate AI night actions, respecting the player's chosen action.
            alive = _solo_alive(game)
            mafia_team = [p for p in alive if p["role"] in {"mafia", "don"}]
            maniacs = [p for p in alive if p["role"] == "maniac"]
            attacks = []
            mafia_targets = [p for p in alive if _solo_team(p["role"]) != "mafia"]
            if mafia_team and mafia_targets and role not in {"mafia", "don"}:
                attacks.append((random.choice(mafia_targets), "mafia"))
            if maniacs and role != "maniac":
                candidates = [p for p in alive if p["role"] != "maniac"]
                if candidates:
                    attacks.append((random.choice(candidates), "maniac"))
            if role in {"mafia", "don"} and target:
                attacks.append((target, "mafia"))
            if role == "maniac" and target:
                attacks.append((target, "maniac"))
            protection_targets = []
            night_lines = []
            morning_lines = []
            if role in {"doctor", "bodyguard"} and target is not None:
                protection_targets.append(target)
                action_label = "Shifokor" if role == "doctor" else "Tansoqchi"
                night_lines.append(f"🩺 <b>{action_label}</b> davolash/himoya qilish uchun yo‘lga chiqdi.")
            for protector in [p for p in alive if p["role"] in {"doctor", "bodyguard"} and not p.get("is_player")]:
                candidates = [p for p in alive if p["id"] != protector["id"]]
                if candidates and random.random() < 0.75:
                    protection_targets.append(random.choice(candidates))
                    action_label = "Shifokor" if protector["role"] == "doctor" else "Tansoqchi"
                    night_lines.append(f"🩺 <b>{action_label}</b> davolash/himoya qilish uchun yo‘lga chiqdi.")
            if any(p["role"] == "detective" and not p.get("is_player") for p in alive):
                night_lines.append("🕵️ <b>Detektiv</b> yashirin tekshiruvga ketdi.")
            if role == "detective" and target is not None:
                night_lines.append("🕵️ Siz tanlagan o‘yinchini yashirin tekshirdingiz.")
            mafia_attack = next((attack for attack in attacks if attack[1] == "mafia"), None)
            if mafia_attack:
                donor = next((p for p in mafia_team if p["role"] == "don"), None)
                title = "Don" if donor else "Mafiya"
                night_lines.append(f"🕴️ <b>{title}</b> o‘ljasini tanladi.")
            maniac_attack = next((attack for attack in attacks if attack[1] == "maniac"), None)
            if maniac_attack:
                night_lines.append("🪓 <b>Manyak</b> nishon tanladi.")
            protected_ids = {p["id"] for p in protection_targets}
            seen_attacks = set()
            inventory = await _inventory(session, uid)
            for victim, source in attacks:
                if victim["id"] in seen_attacks:
                    continue
                seen_attacks.add(victim["id"])
                if victim["id"] in protected_ids:
                    night_lines.append("🛡️ Bir hujum qaytarildi.")
                elif victim.get("is_player") and "lucky_charm" in inventory:
                    inventory.remove("lucky_charm")
                    await _set_value(session, f"u:{uid}:items", json.dumps(inventory, ensure_ascii=False))
                    night_lines.append("🍀 Omad tumori sizga qilingan hujumni qaytardi. Tumor ishlatildi.")
                else:
                    victim["alive"] = False
                    morning_lines.append(f"💀 <b>{escape(victim['name'])}</b> tunda halok bo‘ldi.")
            if not night_lines:
                night_lines.append("🌙 Tun sokin o‘tdi.")
            if attacks and not morning_lines and not any("qaytaril" in line.lower() or "qaytardi" in line.lower() for line in night_lines):
                night_lines.append("🌘 Tun davomida hech kim o‘yindan chiqmadi.")
            winner = _solo_winner(game)
            if not player["alive"] and not winner:
                _solo_autoplay_after_elimination(game)
                spectator_messages = list(game.get("spectator_log", []))
                winner = game.get("winner")
                result_text += ("\n\n" if result_text else "") + "👁️ <b>KUZATUVCHI REJIMI</b>"
            elif winner:
                _solo_finish(game, winner)
            else:
                game["phase"] = "vote"
            game["round"] += 0
            game["log"] = night_lines
            await _set_value(session, f"u:{uid}:solo", json.dumps(game, ensure_ascii=False))
            if game["status"] == "finished":
                user = await session.get(User, uid)
                if user:
                    user.games_played += 1
                    player_won = player["alive"] and winner == _solo_team(player["role"])
                    await record_match_progress(session, uid, player_won)
                    if player_won:
                        user.wins += 1
                        reward = 65 if await _premium_active(session, uid) else 50
                        await _set_value(session, f"u:{uid}:coins", str(await _coins(session, uid) + reward))
                    else:
                        user.losses += 1
            private_result = result_text
            if not player["alive"] and winner:
                private_result += (
                    "\n\n🕯️ <b>Sizning rolingiz:</b> "
                    f"<b>{_solo_role_label(player['role'])}</b>. "
                    "Oxirgi so‘zingizni /lastwords Matn bilan yuboring yoki /skip yozing."
                )
            result_text = "🌅 <b>TONG XABARI</b>"
            if winner:
                result_text += "\n\n" + ("🏆 <b>SHAHAR G‘ALABA QOZONDI!</b>" if winner == "town" else "💀 <b>MAFIYA G‘ALABA QOZONDI!</b>" if winner == "mafia" else "🪓 <b>MANYAK YUTDI!</b>")
            result_text += "\n\n" + ("\n".join(morning_lines) if morning_lines else "🌤️ Bu tun hech kim o‘yindan chiqmadi.")
    await callback.answer("Kuzatuv rejimi davom etmoqda..." if spectator_messages else "Tun yakunlandi.")
    if callback.message and spectator_messages:
        for event_line in spectator_messages:
            await asyncio.sleep(random.uniform(1.2, 2.4))
            await callback.message.answer(event_line)
    if callback.message:
        # Reveal night events one by one to make the Solo game feel alive.
        if private_result:
            await callback.message.answer(private_result)
        for event_line in game.get("log", []):
            await asyncio.sleep(random.uniform(1.0, 1.8))
            await callback.message.answer(event_line)
        await asyncio.sleep(0.8)
        final_text = result_text + ("\n\n☀️ <b>Kunduzgi muhokama va ovoz!</b> Kimni sudga yuborasiz?" if game["status"] == "active" and player["alive"] else "\n\n👁️ Kuzatuvchi rejimi. Oxirgi so‘zingizni aytishingiz yoki kuzatuvdan chiqishingiz mumkin." if not player["alive"] else "\n\n🎮 Yangi o‘yin uchun /solo buyrug‘ini yuboring.")
        keyboard = _solo_keyboard(game, "vote") if not player["alive"] or game["status"] == "active" else None
        await callback.message.answer(final_text, reply_markup=keyboard)


@router.callback_query(F.data == "solo:spectator:lastwords")
async def solo_spectator_lastwords(callback: CallbackQuery) -> None:
    await callback.answer("Oxirgi so‘zingizni yuborish uchun /lastwords Matn yozing. Voz kechish uchun /skip yuboring.", show_alert=True)


@router.callback_query(F.data == "solo:spectator:exit")
async def solo_spectator_exit(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    async with get_session_factory()() as session:
        async with session.begin():
            row = await session.get(BotSetting, f"u:{uid}:solo")
            if row:
                try:
                    game = json.loads(row.value)
                except (TypeError, json.JSONDecodeError):
                    game = {}
                human = next((p for p in game.get("bots", []) if p.get("is_player")), None)
                if human and not human.get("alive", True):
                    game["spectator_left"] = True
                    row.value = json.dumps(game, ensure_ascii=False)
    await callback.answer("Kuzatuvdan chiqdingiz. Yangi o‘yin uchun /solo yuboring.", show_alert=True)
    if callback.message:
        await callback.message.answer(
            "🚪 <b>Kuzatuv rejimidan chiqdingiz.</b>\n\n"
            "O‘yin natijalari saqlanadi. Yangi o‘yin boshlash uchun /solo buyrug‘ini yuboring."
        )


@router.callback_query(F.data.startswith("solo:vote:"))
async def solo_vote(callback: CallbackQuery) -> None:
    try:
        index = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Ovoz noto‘g‘ri.", show_alert=True)
        return

    uid = callback.from_user.id
    game = None
    chosen = None
    likes = 0
    dislikes = 0
    trial_started = False
    result_text = ""
    bot_vote_announcements: list[tuple[str, str, str]] = []
    async with get_session_factory()() as session:
        async with session.begin():
            raw = await _get_value(session, f"u:{uid}:solo", "")
            if not raw:
                await callback.answer("Avval Solo Game boshlang.", show_alert=True)
                return
            game = json.loads(raw)
            if game.get("status") != "active" or game.get("phase") != "vote":
                await callback.answer("Hozir ovoz berish mumkin emas.", show_alert=True)
                return
            player = next((p for p in game["bots"] if p.get("is_player")), None)
            if not player or not player["alive"]:
                await callback.answer("Siz o‘yinda emassiz.", show_alert=True)
                return
            if index < 0 or index >= len(game["bots"]):
                await callback.answer("Ovoz tanlovi noto‘g‘ri.", show_alert=True)
                return
            chosen = game["bots"][index]
            if not chosen["alive"]:
                await callback.answer("Bu o‘yinchi allaqachon o‘yindan chiqqan.", show_alert=True)
                return

            # Every living AI casts a vote. The human's selected vote is added too.
            alive = _solo_alive(game)
            tally = {p["id"]: 0 for p in alive}
            tally[chosen["id"]] += 1
            for voter in alive:
                if voter.get("is_player"):
                    continue
                options = [p for p in alive if p["id"] != voter["id"]]
                if not options:
                    continue
                if _solo_team(voter["role"]) == "mafia":
                    preferred = [p for p in options if _solo_team(p["role"]) != "mafia"]
                elif voter["role"] == "maniac":
                    preferred = [p for p in options if p["role"] != "maniac"]
                else:
                    preferred = [p for p in options if _solo_team(p["role"]) == "mafia"]
                pool = preferred if preferred and random.random() < 0.72 else options
                vote_target = random.choice(pool)
                tally[vote_target["id"]] += 1
                if not voter.get("is_player"):
                    comment = random.choice([
                        f"{vote_target['name']} menga shubhali ko‘rinyapti.",
                        f"Menimcha, {vote_target['name']} haqida gaplashish kerak.",
                        f"Hozircha {vote_target['name']}ga ovoz beraman.",
                        f"Dalil kam, lekin {vote_target['name']}ni tanlayman.",
                    ])
                    bot_vote_announcements.append((voter["name"], vote_target["name"], comment))

            max_votes = max(tally.values()) if tally else 0
            leaders = [p for p in alive if tally[p["id"]] == max_votes]
            vote_lines = [
                f"• {'🧑 Siz' if p.get('is_player') else p['name']} — <b>{tally[p['id']]}</b> ovoz"
                for p in sorted(alive, key=lambda person: (-tally[person["id"]], person["name"]))
            ]
            result_text = "🗳️ <b>KUNDUZGI OVOZ NATIJALARI</b>\n━━━━━━━━━━━━━━━━━━\n"
            result_text += "\n".join(vote_lines) + "\n\n"

            if len(leaders) != 1:
                result_text += "🤝 <b>OVOZLAR TENG!</b> Hech kim sudga yuborilmadi."
                game["round"] += 1
                game["phase"] = "night"
                game["night_action"] = None
                await _set_value(session, f"u:{uid}:solo", json.dumps(game, ensure_ascii=False))
            else:
                chosen = leaders[0]
                eligible = [p for p in alive if not p.get("is_player") and p["id"] != chosen["id"]]
                for voter in eligible:
                    if _solo_team(voter["role"]) == "mafia":
                        favor_like = _solo_team(chosen["role"]) != "mafia"
                    elif voter["role"] == "maniac":
                        favor_like = chosen["role"] != "maniac"
                    else:
                        favor_like = _solo_team(chosen["role"]) == "mafia"
                    if random.random() < (0.68 if favor_like else 0.32):
                        likes += 1
                    else:
                        dislikes += 1
                game["phase"] = "trial"
                game["trial"] = {
                    "target_id": chosen["id"],
                    "target_name": "Siz" if chosen.get("is_player") else chosen["name"],
                    "target_role": chosen["role"],
                    "likes": likes,
                    "dislikes": dislikes,
                }
                await _set_value(session, f"u:{uid}:solo", json.dumps(game, ensure_ascii=False))
                trial_started = True

    await callback.answer("Bot-o‘yinchilar navbatma-navbat ovoz bermoqda...")
    if callback.message:
        for voter_name, target_name, comment in bot_vote_announcements:
            await asyncio.sleep(random.uniform(0.8, 1.7))
            await callback.message.answer(
                f"💬 <b>{voter_name}:</b> {comment}\n🗳️ Ovoz: <b>{target_name}</b>"
            )

    if trial_started:
        trial_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"👍 Like — {likes} + sizning ovozingiz", callback_data="solo:trial:like")],
            [InlineKeyboardButton(text=f"👎 Dislike — {dislikes} + sizning ovozingiz", callback_data="solo:trial:dislike")],
        ])
        target_label = "🧑 Siz" if chosen.get("is_player") else chosen["name"]
        trial_text = (
            result_text
            + "⚖️ <b>SUDGA CHIQARILDI</b>\n"
            + f"👤 Eng ko‘p ovoz olgan: <b>{target_label}</b>\n"
            + f"👍 Like: <b>{likes}</b>\n"
            + f"👎 Dislike: <b>{dislikes}</b>\n\n"
            + "Like ko‘p bo‘lsa — osiladi. Dislike ko‘p yoki teng bo‘lsa — osilmaydi."
        )
        if callback.message:
            try:
                await callback.message.answer_animation(animation=SOLO_GIF["vote"], caption=trial_text, reply_markup=trial_keyboard)
            except Exception:
                await callback.message.answer(trial_text, reply_markup=trial_keyboard)
    else:
        if callback.message:
            result_text += f"\n🌙 <b>{game['round']}-tun boshlandi.</b>"
            try:
                await callback.message.answer_animation(animation=SOLO_GIF["night"], caption=result_text, reply_markup=_solo_keyboard(game, "night"))
            except Exception:
                await callback.message.answer(result_text, reply_markup=_solo_keyboard(game, "night"))


@router.callback_query(F.data.in_({"solo:trial:like", "solo:trial:dislike"}))
async def solo_trial_react(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    reaction = (callback.data or "").rsplit(":", 1)[-1]
    game = None
    result_text = ""
    spectator_messages: list[str] = []
    async with get_session_factory()() as session:
        async with session.begin():
            raw = await _get_value(session, f"u:{uid}:solo", "")
            if not raw:
                await callback.answer("Avval Solo Game boshlang.", show_alert=True)
                return
            game = json.loads(raw)
            if game.get("status") != "active" or game.get("phase") != "trial" or not game.get("trial"):
                await callback.answer("Bu hukm allaqachon chiqarilgan.", show_alert=True)
                return
            player = next((p for p in game["bots"] if p.get("is_player")), None)
            if not player or not player["alive"]:
                await callback.answer("Siz o‘yinda emassiz.", show_alert=True)
                return

            trial = game["trial"]
            likes = int(trial["likes"]) + (1 if reaction == "like" else 0)
            dislikes = int(trial["dislikes"]) + (1 if reaction == "dislike" else 0)
            target = next((p for p in game["bots"] if p["id"] == trial["target_id"]), None)
            target_is_player = bool(target and target.get("is_player"))
            result_text = (
                "⚖️ <b>MAFIA SUDI — YAKUNIY HUKM</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"👤 Sudlanuvchi: <b>{trial['target_name']}</b>\n"
                f"👍 Like: <b>{likes}</b>\n"
                f"👎 Dislike: <b>{dislikes}</b>\n\n"
            )
            hanged = likes > dislikes
            charm_saved = False
            if hanged and target_is_player:
                inventory = await _inventory(session, uid)
                if "lucky_charm" in inventory:
                    inventory.remove("lucky_charm")
                    await _set_value(session, f"u:{uid}:items", json.dumps(inventory, ensure_ascii=False))
                    hanged = False
                    charm_saved = True
            if charm_saved:
                result_text += "🍀 <b>Omad tumori ishga tushdi!</b> Siz suddan qutuldingiz. Tumor ishlatildi."
            elif hanged and target and target["alive"]:
                target["alive"] = False
                result_text += (
                    f"🔨 <b>{trial['target_name']} OSILDI!</b>\n"
                    f"🎭 Roli: <b>{_solo_role_label(trial['target_role'])}</b>."
                )
            elif likes == dislikes:
                result_text += "🤝 <b>OVOZLAR TENG.</b> Hech kim osilmaydi."
            else:
                result_text += "🕊️ <b>DISLIKE KO‘P.</b> Sudlanuvchi ozod qilindi."

            if target_is_player and hanged:
                _solo_autoplay_after_elimination(game)
                spectator_messages = list(game.get("spectator_log", []))
                result_text += "👁️ <b>KUZATUVCHI REJIMI</b>"
                winner = game.get("winner")
            else:
                winner = _solo_winner(game)
                if winner:
                    _solo_finish(game, winner)
                else:
                    game["round"] += 1
                    game["phase"] = "night"
                    game["night_action"] = None

            game.pop("trial", None)
            await _set_value(session, f"u:{uid}:solo", json.dumps(game, ensure_ascii=False))
            if game["status"] == "finished":
                user = await session.get(User, uid)
                if user:
                    user.games_played += 1
                    player_won = winner == _solo_team(player["role"]) and not target_is_player
                    await record_match_progress(session, uid, player_won)
                    if player_won:
                        user.wins += 1
                        reward = 65 if await _premium_active(session, uid) else 50
                        coins = await _coins(session, uid) + reward
                        await _set_value(session, f"u:{uid}:coins", str(coins))
                        result_text += f"\n\n🏆 <b>G‘ALABA!</b> +{reward} 🪙" + (" · 👑 Premium bonus" if reward > 50 else "")
                    else:
                        user.losses += 1
                        result_text += "\n\n💔 <b>O‘YIN TUGADI.</b>"
                result_text += "\nG‘olib: " + ("🏙️ Shahar" if winner == "town" else "🔪 Mafia" if winner == "mafia" else "🪓 Manyak")

    await callback.answer("Kuzatuv rejimi davom etmoqda..." if spectator_messages else "Hukm chiqarildi.")
    if callback.message and spectator_messages:
        for event_line in spectator_messages:
            await asyncio.sleep(random.uniform(1.2, 2.4))
            await callback.message.answer(event_line)
    if callback.message:
        if game["status"] == "active":
            result_text += f"\n\n🌙 <b>{game['round']}-tun boshlandi.</b>"
            keyboard = _solo_keyboard(game, "night")
            try:
                await callback.message.answer_animation(animation=SOLO_GIF["night"], caption=result_text, reply_markup=keyboard)
            except Exception:
                await callback.message.answer(result_text, reply_markup=keyboard)
        else:
            result_text += "\n\n🎮 Yangi o‘yin uchun /solo buyrug‘ini yuboring."
            try:
                await callback.message.answer_animation(animation=SOLO_GIF["win"], caption=result_text)
            except Exception:
                await callback.message.answer(result_text)
