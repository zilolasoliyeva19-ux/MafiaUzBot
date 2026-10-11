import json
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from app.database import get_session_factory
from app.models import BotSetting

router = Router(name="social")


@router.message(Command("lastwords"))
async def last_words(message: Message) -> None:
    if not message.from_user:
        return
    body = (message.text or "").partition(" ")[2].strip()
    if not body:
        await message.answer("Oxirgi so‘zingizni yozing: <code>/lastwords Men sizlarni unutmayman...</code>")
        return
    if len(body) > 300:
        await message.answer("Oxirgi so‘z 300 belgidan oshmasin.")
        return

    uid = message.from_user.id
    recipients = []
    announcement = ""
    async with get_session_factory()() as session:
        async with session.begin():
            # Prefer an active multiplayer game, so an old Solo result cannot intercept the command.
            rows = list((await session.scalars(
                select(BotSetting).where(BotSetting.key.like("roomgame:%"))
            )).all())
            found = None
            for row in rows:
                try:
                    game = json.loads(row.value)
                except (TypeError, json.JSONDecodeError):
                    continue
                player = next((p for p in game.get("players", []) if p.get("id") == uid), None)
                if player and not player.get("alive", True):
                    found = (row, game, player)
                    if game.get("status") == "active":
                        break
            if found:
                row, game, player = found
                game.setdefault("last_words", {})[str(uid)] = body
                row.value = json.dumps(game, ensure_ascii=False)
                recipients = [p.get("id") for p in game.get("players", []) if p.get("id")]
                name = escape(player.get("name", "O‘yinchi"))
                announcement = f"🕯️ <b>{name}ning oxirgi so‘zi:</b>\n{escape(body)}"
            else:
                solo_raw = await session.get(BotSetting, f"u:{uid}:solo")
                solo_game = None
                if solo_raw:
                    try:
                        solo_game = json.loads(solo_raw.value)
                    except (TypeError, json.JSONDecodeError):
                        pass
                solo_player = next((p for p in solo_game.get("bots", []) if p.get("is_player")), None) if solo_game else None
                if solo_player and not solo_player.get("alive", True):
                    solo_game["last_words"] = body
                    solo_raw.value = json.dumps(solo_game, ensure_ascii=False)
                    await message.answer("🕯️ Oxirgi so‘zingiz Solo o‘yin tarixiga saqlandi. Siz kuzatuvchi rejimidasiz.")
                    return
                await message.answer("🕯️ Oxirgi so‘z faqat o‘yindan chiqqaningizdan keyin yoziladi.")
                return
    delivered = 0
    for recipient in recipients:
        try:
            await message.bot.send_message(recipient, announcement)
            delivered += 1
        except Exception:
            pass
    await message.answer(f"🕯️ Oxirgi so‘zingiz yuborildi ({delivered} o‘yinchiga). Siz tirik qolganlar o‘yinini kuzatishingiz mumkin.")
