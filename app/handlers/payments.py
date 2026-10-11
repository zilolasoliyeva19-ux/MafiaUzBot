import json
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select

from app.database import get_session_factory
from app.models import BotSetting, User

router = Router(name="payments")


@router.message(Command("stars"))
@router.message(F.text == "⭐ Stars / Premium")
async def stars_shop(message: Message) -> None:
    await message.answer(
        "⭐ <b>MafiaUzBot Premium</b>\n\n"
        "🪙 <b>1 000 tanga</b> — 50 Telegram Stars\n"
        "👑 <b>VIP 30 kun</b> — 100 Telegram Stars\n\n"
        "Xarid qilish uchun buyruqlardan foydalaning:\n"
        "/buycoins — 1 000 tanga\n"
        "/buyvip — 30 kunlik VIP"
    )


async def _invoice(message: Message, payload: str, title: str, description: str, stars: int) -> None:
    await message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=stars)],
    )


@router.message(Command("buycoins"))
async def buy_coins(message: Message) -> None:
    if message.from_user:
        await _invoice(message, f"stars:coins1000:{message.from_user.id}",
                       "1 000 o‘yin tangasi", "MafiaUzBot balansiga 1 000 tanga qo‘shiladi.", 50)


@router.message(Command("buyvip"))
async def buy_vip(message: Message) -> None:
    if message.from_user:
        await _invoice(message, f"stars:vip30:{message.from_user.id}",
                       "VIP — 30 kun", "Profilingizga 30 kunlik VIP maqom beriladi.", 100)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    payload = query.invoice_payload
    parts = payload.split(":")
    valid = (
        query.currency == "XTR"
        and len(parts) == 3
        and parts[0] == "stars"
        and parts[2].isdigit()
        and int(parts[2]) == query.from_user.id
        and ((parts[1] == "coins1000" and query.total_amount == 50)
             or (parts[1] == "vip30" and query.total_amount == 100))
    )
    await query.answer(ok=valid, error_message=None if valid else "To‘lov ma’lumotlari noto‘g‘ri. Qayta urinib ko‘ring.")


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if not message.from_user or not payment:
        return
    payload = payment.invoice_payload.split(":")
    if len(payload) != 3 or payload[0] != "stars" or not payload[2].isdigit():
        return
    uid = message.from_user.id
    if int(payload[2]) != uid or payment.currency != "XTR":
        return
    charge_key = f"payment:charge:{payment.telegram_payment_charge_id}"
    async with get_session_factory()() as session:
        async with session.begin():
            if await session.get(BotSetting, charge_key):
                await message.answer("✅ Bu to‘lov oldin qayta ishlangan.")
                return
            session.add(BotSetting(key=charge_key, value=json.dumps({
                "user_id": uid, "payload": payment.invoice_payload, "amount": payment.total_amount,
                "paid_at": datetime.now(timezone.utc).isoformat(),
            })))
            user = await session.get(User, uid)
            if payload[1] == "coins1000" and payment.total_amount == 50:
                key = f"u:{uid}:coins"
                row = await session.get(BotSetting, key)
                coins = int(row.value) if row else 100
                if row is None:
                    session.add(BotSetting(key=key, value=str(coins + 1000)))
                else:
                    row.value = str(coins + 1000)
                reply = "🎉 To‘lov muvaffaqiyatli! Balansingizga 1 000 🪙 qo‘shildi."
            elif payload[1] == "vip30" and payment.total_amount == 100:
                key = f"u:{uid}:vip_until"
                row = await session.get(BotSetting, key)
                now = datetime.now(timezone.utc)
                old_until = None
                if row:
                    try:
                        old_until = datetime.fromisoformat(row.value)
                    except ValueError:
                        old_until = None
                base = old_until if old_until and old_until > now else now
                until = base + timedelta(days=30)
                if row is None:
                    session.add(BotSetting(key=key, value=until.isoformat()))
                else:
                    row.value = until.isoformat()
                reply = f"👑 VIP faollashtirildi! Amal qilish muddati: <b>{until.strftime('%Y-%m-%d %H:%M UTC')}</b>."
            else:
                await message.answer("⚠️ To‘lov qabul qilindi, lekin mahsulot mos kelmadi. Administratorga murojaat qiling.")
                return
    await message.answer(reply)
