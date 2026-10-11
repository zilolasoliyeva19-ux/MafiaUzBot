import json
import random
from collections import Counter
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database import get_session_factory
from app.models import BotSetting, GameMatch, GameParticipant, GameRoom, User

router = Router(name="gameplay")
MAFIA = "mafia"
SPECIALS = {"doctor", "detective"}


async def _load(session, key: str) -> dict | None:
    row = await session.get(BotSetting, key)
    return json.loads(row.value) if row else None


async def _save(session, key: str, value: dict) -> None:
    row = await session.get(BotSetting, key)
    payload = json.dumps(value, ensure_ascii=False)
    if row is None:
        session.add(BotSetting(key=key, value=payload))
    else:
        row.value = payload


async def _players(session, room_id: int):
    result = await session.execute(
        select(GameParticipant, User)
        .join(User, User.telegram_id == GameParticipant.user_id)
        .where(GameParticipant.room_id == room_id)
        .order_by(GameParticipant.joined_at)
    )
    return list(result.all())


def _role_plan(count: int) -> list[str]:
    roles = [MAFIA] * (2 if count >= 7 else 1)
    roles += ["doctor", "detective"]
    roles += ["citizen"] * (count - len(roles))
    return roles


def _role_name(role: str) -> str:
    return {
        "mafia": "🔪 Mafia",
        "doctor": "🩺 Doktor",
        "detective": "🕵️ Detektiv",
        "citizen": "👨‍🌾 Tinch aholi",
    }.get(role, role)


def _target_keyboard(room_id: int, players: list[dict], action: str, actor_id: int) -> InlineKeyboardMarkup:
    rows = []
    for player in players:
        if not player["alive"] or player["id"] == actor_id:
            continue
        rows.append([InlineKeyboardButton(
            text=f"🎯 {player['name']}",
            callback_data=f"game:{action}:{room_id}:{player['id']}",
        )])
    if action == "night_doctor":
        rows.append([InlineKeyboardButton(text="🛡️ Hech kimni davolamaslik", callback_data=f"game:night_skip:{room_id}:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _winner(game: dict) -> str | None:
    alive = [p for p in game["players"] if p["alive"]]
    mafia = sum(p["role"] == MAFIA for p in alive)
    others = len(alive) - mafia
    if mafia == 0:
        return "citizens"
    if mafia >= others:
        return "mafia"
    return None


async def _tell_all(bot, game: dict, text: str) -> None:
    for player in game["players"]:
        try:
            await bot.send_message(player["id"], text)
        except Exception:
            # A player must open the bot privately before it can send them a DM.
            pass


async def _finish(bot, session, room: GameRoom, game: dict, winner: str) -> None:
    game["status"] = "finished"
    game["winner"] = winner
    room.status = "finished"
    for player in game["players"]:
        db_user = await session.get(User, player["id"])
        if db_user:
            db_user.games_played += 1
            if (winner == "mafia" and player["role"] == MAFIA) or (winner == "citizens" and player["role"] != MAFIA):
                db_user.wins += 1
                key = f"u:{player['id']}:coins"
                wallet = await session.get(BotSetting, key)
                coins = int(wallet.value) if wallet else 100
                if wallet is None:
                    session.add(BotSetting(key=key, value="150"))
                else:
                    wallet.value = str(coins + 50)
            else:
                db_user.losses += 1
    await _save(session, f"roomgame:{room.id}", game)
    role_lines = "\n".join(f"• {p['name']} — {_role_name(p['role'])}" for p in game["players"])
    team = "🔪 Mafia" if winner == "mafia" else "🕊️ Tinch aholi"
    await _tell_all(bot, game, f"🏁 <b>O‘yin tugadi!</b>\nG‘olib: {team}\nHar bir g‘olib +50 🪙 oldi.\n\n<b>Rollar:</b>\n{role_lines}")


async def _start_night(bot, session, room: GameRoom, game: dict) -> None:
    game["phase"] = "night"
    game["round"] += 1
    game["actions"] = {}
    await _save(session, f"roomgame:{room.id}", game)
    for player in game["players"]:
        if not player["alive"]:
            continue
        role = player["role"]
        if role == "mafia":
            targets = [p for p in game["players"] if p["alive"] and p["role"] != MAFIA]
            prompt = "🌙 <b>Tun.</b> Mafiya sifatida kimni yo‘q qilmoqchisiz?"
            action = "night_mafia"
        elif role == "doctor":
            targets = [p for p in game["players"] if p["alive"]]
            prompt = "🌙 <b>Tun.</b> Kimni qutqarasiz?"
            action = "night_doctor"
        elif role == "detective":
            targets = [p for p in game["players"] if p["alive"] and p["id"] != player["id"]]
            prompt = "🌙 <b>Tun.</b> Kimning rolini tekshirasiz?"
            action = "night_detective"
        else:
            continue
        try:
            await bot.send_message(player["id"], prompt, reply_markup=_target_keyboard(room.id, targets, action, player["id"]))
        except Exception:
            pass


async def _start_day(bot, session, room: GameRoom, game: dict, killed: int | None, saved: bool) -> None:
    if killed is not None and not saved:
        for player in game["players"]:
            if player["id"] == killed:
                player["alive"] = False
                break
    winner = _winner(game)
    if winner:
        await _finish(bot, session, room, game, winner)
        return
    game["phase"] = "day"
    game["actions"] = {}
    await _save(session, f"roomgame:{room.id}", game)
    dead_name = next((p["name"] for p in game["players"] if p["id"] == killed), None)
    news = f"☀️ <b>{game['round']}-kun boshlandi!</b>\n"
    if killed is None:
        news += "Bu kecha hech kim nishonga olinmadi.\n"
    elif saved:
        news += "🩺 Doktor kimnidir qutqarib qoldi!\n"
    else:
        news += f"💀 Kechasi {dead_name} o‘yindan chiqdi. Uning roli oshkor qilinmaydi.\n"
    alive = [p for p in game["players"] if p["alive"]]
    news += "\nMuhokama qiling, so‘ng kimni chiqarishni ovoz bilan tanlang."
    await _tell_all(bot, game, news)
    for player in alive:
        try:
            await bot.send_message(
                player["id"],
                "🗳️ <b>Kunduzgi ovoz</b> — kimni o‘yindan chiqaramiz?",
                reply_markup=_target_keyboard(room.id, game["players"], "vote", player["id"]),
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("game:start:"))
async def start_match(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    try:
        room_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Xona kodi noto‘g‘ri.", show_alert=True)
        return
    async with get_session_factory()() as session:
        async with session.begin():
            room = await session.get(GameRoom, room_id, with_for_update=True)
            if room is None or room.status != "lobby":
                await callback.answer("Bu xona endi boshlashga tayyor emas.", show_alert=True)
                return
            if room.owner_id != callback.from_user.id:
                await callback.answer("O‘yinni faqat xona egasi boshlaydi.", show_alert=True)
                return
            rows = await _players(session, room_id)
            if len(rows) < room.min_players:
                await callback.answer(f"Kamida {room.min_players} o‘yinchi kerak.", show_alert=True)
                return
            random.shuffle(rows)
            roles = _role_plan(len(rows))
            random.shuffle(roles)
            game_players = []
            for (participant, user), role in zip(rows, roles):
                participant.role = role
                participant.is_alive = True
                game_players.append({"id": user.telegram_id, "name": user.display_name, "role": role, "alive": True})
            match = GameMatch(room_id=room.id, status="active", phase="night")
            session.add(match)
            room.status = "active"
            game = {"room_id": room.id, "match_id": None, "phase": "night", "round": 1, "status": "active", "actions": {}, "players": game_players}
            await session.flush()
            game["match_id"] = match.id
            await _save(session, f"roomgame:{room.id}", game)
    await callback.answer("O‘yin boshlandi!")
    if callback.message:
        try:
            await callback.message.edit_text(f"🎭 <b>Mafia o‘yini boshlandi!</b>\nXona: <code>{room.room_code}</code>\nRollar o‘yinchilarga shaxsiy xabarda yuborildi.")
        except Exception:
            pass
    for player in game_players:
        extra = "\nMafiya jamoadoshlari: " + ", ".join(p["name"] for p in game_players if p["role"] == MAFIA and p["id"] != player["id"]) if player["role"] == MAFIA else ""
        try:
            await callback.bot.send_message(player["id"], f"🎭 <b>Sizning rolingiz:</b> {_role_name(player['role'])}\nXona: <code>{room.room_code}</code>{extra}\n\nRolingizni sir saqlang.")
        except Exception:
            pass
    async with session.begin():
        await _start_night(callback.bot, session, room, game)


@router.callback_query(F.data.startswith("game:night_"))
async def night_action(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Tanlov yaroqsiz.", show_alert=True)
        return
    action, room_id, target_raw = parts[1], int(parts[2]), int(parts[3])
    actor_id = callback.from_user.id
    async with get_session_factory()() as session:
        async with session.begin():
            room = await session.get(GameRoom, room_id, with_for_update=True)
            game = await _load(session, f"roomgame:{room_id}")
            if not room or not game or game["status"] != "active" or game["phase"] != "night":
                await callback.answer("Tun bosqichi tugagan.", show_alert=True)
                return
            actor = next((p for p in game["players"] if p["id"] == actor_id and p["alive"]), None)
            target = next((p for p in game["players"] if p["id"] == target_raw and p["alive"]), None)
            if not actor or not target or actor["role"] not in SPECIALS | {MAFIA}:
                if action != "night_skip" or not actor or actor["role"] != "doctor":
                    await callback.answer("Bu amal sizga ruxsat etilmagan.", show_alert=True)
                    return
            if actor_id in game["actions"]:
                await callback.answer("Siz bu tun uchun tanlov qilgansiz.", show_alert=True)
                return
            if action == "night_mafia" and actor["role"] == MAFIA and target["role"] != MAFIA:
                game["actions"][str(actor_id)] = {"type": "mafia", "target": target_raw}
            elif action == "night_doctor" and actor["role"] == "doctor":
                game["actions"][str(actor_id)] = {"type": "doctor", "target": target_raw}
            elif action == "night_skip" and actor["role"] == "doctor":
                game["actions"][str(actor_id)] = {"type": "doctor", "target": None}
            elif action == "night_detective" and actor["role"] == "detective" and actor_id != target_raw:
                game["actions"][str(actor_id)] = {"type": "detective", "target": target_raw}
                await callback.bot.send_message(actor_id, f"🕵️ Tekshiruv: {target['name']} {'🔪 mafiya' if target['role'] == MAFIA else '🕊️ mafiya emas'}.")
            else:
                await callback.answer("Bu nishonni tanlay olmaysiz.", show_alert=True)
                return
            await _save(session, f"roomgame:{room_id}", game)
            alive = [p for p in game["players"] if p["alive"]]
            required = sum(p["role"] in SPECIALS | {MAFIA} for p in alive)
            done = sum(1 for p in alive if str(p["id"]) in game["actions"] and p["role"] in SPECIALS | {MAFIA})
            if done >= required:
                actions = list(game["actions"].values())
                mafia_targets = [a["target"] for a in actions if a["type"] == "mafia" and a["target"] is not None]
                killed = Counter(mafia_targets).most_common(1)[0][0] if mafia_targets else None
                saved = any(a["type"] == "doctor" and a["target"] == killed for a in actions)
                await _start_day(callback.bot, session, room, game, killed, saved)
    await callback.answer("Tanlov qabul qilindi.")


@router.callback_query(F.data.startswith("game:vote:"))
async def day_vote(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Ovoz noto‘g‘ri.", show_alert=True)
        return
    room_id, target_id = int(parts[2]), int(parts[3])
    actor_id = callback.from_user.id
    async with get_session_factory()() as session:
        async with session.begin():
            room = await session.get(GameRoom, room_id, with_for_update=True)
            game = await _load(session, f"roomgame:{room_id}")
            if not room or not game or game["status"] != "active" or game["phase"] != "day":
                await callback.answer("Ovoz berish tugagan.", show_alert=True)
                return
            actor = next((p for p in game["players"] if p["id"] == actor_id and p["alive"]), None)
            target = next((p for p in game["players"] if p["id"] == target_id and p["alive"]), None)
            if not actor or not target or actor_id in game["actions"] or actor_id == target_id:
                await callback.answer("Ovoz berib bo‘lmaydi.", show_alert=True)
                return
            game["actions"][str(actor_id)] = {"type": "vote", "target": target_id}
            await _save(session, f"roomgame:{room_id}", game)
            alive = [p for p in game["players"] if p["alive"]]
            if all(str(p["id"]) in game["actions"] for p in alive):
                votes = Counter(a["target"] for a in game["actions"].values() if a.get("type") == "vote")
                highest = votes.most_common()
                if highest and (len(highest) == 1 or highest[0][1] > highest[1][1]):
                    eliminated_id = highest[0][0]
                    eliminated = next(p for p in game["players"] if p["id"] == eliminated_id)
                    eliminated["alive"] = False
                    summary = f"⚖️ Ovoz natijasi: {eliminated['name']} o‘yindan chiqarildi. Rol: {_role_name(eliminated['role'])}."
                else:
                    summary = "⚖️ Ovozlar teng. Hech kim o‘yindan chiqarilmadi."
                await _tell_all(callback.bot, game, summary)
                winner = _winner(game)
                if winner:
                    await _finish(callback.bot, session, room, game, winner)
                else:
                    await _start_night(callback.bot, session, room, game)
    await callback.answer("Ovozingiz qabul qilindi.")
