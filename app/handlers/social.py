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
@router.message(Command("skip"))
async def last_words(message: Message) -> None:
    if not message.from_user:
        return
    command = (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()
    is_skip = command == "/skip"
    body = (message.text or "").partition(" ")[2].strip()
    if not is_skip and not body:
        await message.answer(
            "🕯️ Oxirgi so‘zingizni <code>/lastwords Matn</code> bilan yuboring. "
            "Yozishni istamasangiz, <code>/skip</code> yuboring."
        )
        return
    if not is_skip and len(body) > 300:
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
                saved_body = "⏭️ Oxirgi so‘zdan voz kechdi." if is_skip else body
                game.setdefault("last_words", {})[str(uid)] = saved_body
                row.value = json.dumps(game, ensure_ascii=False)
                recipients = [p.get("id") for p in game.get("players", []) if p.get("id")]
                name = escape(player.get("name", "O‘yinchi"))
                announcement = (
                    f"⏭️ <b>{name}</b> oxirgi so‘z aytmaslikni tanladi."
                    if is_skip else f"🕯️ <b>{name}ning oxirgi so‘zi:</b>\n{escape(body)}"
                )
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
                    solo_game["last_words"] = "⏭️ Oxirgi so‘zdan voz kechdi." if is_skip else body
                    solo_raw.value = json.dumps(solo_game, ensure_ascii=False)
                    await message.answer(
                        "⏭️ Oxirgi so‘zdan voz kechildi. Kuzatuv rejimi davom etadi."
                        if is_skip else "🕯️ Oxirgi so‘zingiz Solo o‘yin tarixiga saqlandi. Siz kuzatuvchi rejimidasiz."
                    )
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
    await message.answer(
        f"⏭️ Oxirgi so‘zdan voz kechildi ({delivered} o‘yinchiga xabar berildi). Kuzatuv rejimi davom etadi."
        if is_skip else f"🕯️ Oxirgi so‘zingiz yuborildi ({delivered} o‘yinchiga). Siz tirik qolganlar o‘yinini kuzatishingiz mumkin."
    )
