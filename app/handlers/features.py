import asyncio
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
    "intro": "https://media1.giphy.com/media/vXgzDdnQ8an6sLS8CB/200.gif",
    "night": "https://media1.giphy.com/media/UPLqiMW16vXsfpuHCP/200.gif",
    "vote": "https://media1.giphy.com/media/iHcxDxXqOAC5o0639Q/200.gif",
    "win": "https://media1.giphy.com/media/cZ7rmKfFYOvYI/200.gif",
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
    rows = []
    for i, bot in enumerate(game["bots"]):
        if not bot["alive"]:
            continue
        if bot.get("is_player") and mode != "vote":
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
    narration = ["👁️ Siz o‘yindan chiqdingiz. Endi qolgan o‘yinchilar avtomatik davom etadi."]
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

        # Day vote among surviving bots.
        alive = _solo_alive(game)
        tally = {p["id"]: 0 for p in alive}
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
            tally[random.choice(pool)["id"]] += 1
        if tally:
            high = max(tally.values())
            leaders = [p for p in alive if tally[p["id"]] == high]
            if len(leaders) == 1 and random.random() < 0.82:
                nominee = leaders[0]
                nominee["alive"] = False
                narration.append(f"🗳️ Ovoz bilan {nominee['name']} ({_solo_role_label(nominee['role'])}) chiqarildi.")
            else:
                narration.append("🗳️ Ovozlar tenglashdi, hech kim chiqarilmadi.")

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
        "👥 Stol atrofidagi jami o‘yinchilar sonini tanlang. Siz ham shu songa kiradi.\n\n"
        "🎲 Rolingiz tasodifiy beriladi: mafiya, Don, shifokor, detektiv, tansoqchi, manyak yoki fuqaro.\n"
        "🌙 Tun → ☀️ muhokama va ovoz → 🏁 g‘alaba shartigacha davom etadi.",
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
            if target_index is not None and (target is None or not target["alive"] or target.get("is_player")):
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
            protection_target = target if role in {"doctor", "bodyguard"} else None
            for protector in [p for p in alive if p["role"] in {"doctor", "bodyguard"} and not p.get("is_player")]:
                candidates = [p for p in alive if p["id"] != protector["id"]]
                if candidates and random.random() < 0.75:
                    if random.random() < 0.65:
                        protection_target = random.choice(candidates)
            night_lines = []
            protected_ids = {protection_target["id"]} if protection_target else set()
            seen_attacks = set()
            for victim, source in attacks:
                if victim["id"] in seen_attacks:
                    continue
                seen_attacks.add(victim["id"])
                if victim["id"] in protected_ids:
                    night_lines.append(f"🛡️ {victim['name']}ga qilingan hujum qaytarildi.")
                else:
                    victim["alive"] = False
                    night_lines.append(f"💀 {victim['name']} tunda halok bo‘ldi.")
            if not night_lines:
                night_lines.append("🌅 Tun tinch o‘tdi — hech kim halok bo‘lmadi.")
            winner = _solo_winner(game)
            if not player["alive"] and not winner:
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
                    if player["alive"] and winner == _solo_team(player["role"]):
                        user.wins += 1
                        await _set_value(session, f"u:{uid}:coins", str(await _coins(session, uid) + 50))
                    else:
                        user.losses += 1
            result_text += ("\n\n" if result_text else "") + "🌅 <b>TONG XABARI</b>\n" + "\n".join(night_lines)
            if winner:
                result_text += "\n\n" + ("🏆 <b>SHAHAR G‘ALABA QOZONDI!</b>" if winner == "town" else "💀 <b>MAFIYA G‘ALABA QOZONDI!</b>" if winner == "mafia" else "🪓 <b>MANYAK YUTDI!</b>")
    if callback.message and spectator_messages:
        for event_line in spectator_messages:
            await asyncio.sleep(random.uniform(1.2, 2.4))
            await callback.message.answer(event_line)
    if callback.message:
        final_text = result_text + ("\n\n☀️ <b>Kunduzgi ovoz:</b> kimni chiqarasiz?" if game["status"] == "active" else "\n\n🎮 Yangi o‘yin uchun /solo buyrug‘ini yuboring.")
        try:
            await callback.message.answer_animation(
                animation=SOLO_GIF["night"], caption=final_text,
                reply_markup=_solo_keyboard(game, "vote") if game["status"] == "active" else None,
            )
        except Exception:
            await callback.message.answer(final_text, reply_markup=_solo_keyboard(game, "vote") if game["status"] == "active" else None)
    await callback.answer("Tun yakunlandi.")


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
            if hanged and target and target["alive"]:
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
                    if winner == _solo_team(player["role"]) and not target_is_player:
                        user.wins += 1
                        coins = await _coins(session, uid) + 50
                        await _set_value(session, f"u:{uid}:coins", str(coins))
                        result_text += "\n\n🏆 <b>G‘ALABA!</b> +50 🪙"
                    else:
                        user.losses += 1
                        result_text += "\n\n💔 <b>O‘YIN TUGADI.</b>"
                result_text += "\nG‘olib: " + ("🏙️ Shahar" if winner == "town" else "🔪 Mafia" if winner == "mafia" else "🪓 Manyak")

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
    await callback.answer("Hukm chiqarildi.")
