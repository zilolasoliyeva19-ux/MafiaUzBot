import json
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from app.database import get_session_factory
from app.models import BotSetting

router = Router(name="payments")

PREMIUM_DAYS = 30
PREMIUM_STARS = 50
MAX_COIN_PURCHASE = 10000


def _stars_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🪙 10 tanga · 10 ⭐", callback_data="stars:buy:coins:10"),
            InlineKeyboardButton(text="🪙 50 tanga · 50 ⭐", callback_data="stars:buy:coins:50"),
        ],
        [
            InlineKeyboardButton(text="🪙 100 tanga · 100 ⭐", callback_data="stars:buy:coins:100"),
            InlineKeyboardButton(text="💎 1 olmos · 2 ⭐", callback_data="stars:buy:diamond:1"),
        ],
        [InlineKeyboardButton(text="👑 Premium · 50 ⭐ / 30 kun", callback_data="stars:buy:premium:30")],
    ])


@router.message(Command("stars"))
@router.message(F.text == "⭐ Stars / Premium")
async def stars_shop(message: Message) -> None:
    await message.answer(
        "✨ <b>MAFIA UZ — STARS DO‘KONI</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🪙 <b>1 ⭐ = 1 tanga</b>\n"
        "💎 <b>2 ⭐ = 1 olmos</b>\n"
        f"👑 <b>Premium — {PREMIUM_STARS} ⭐ / {PREMIUM_DAYS} kun</b>\n\n"
        "Premium imtiyozlari:\n"
        "• 👑 Profilingizda Premium belgisi\n"
        "• 🎁 G‘alaba uchun 25% ko‘proq tanga\n"
        "• 💎 Maxsus olmosli buyumlar\n\n"
        "Pastdagi tugmalardan mahsulot va miqdorni tanlang. Xarid tasdiqlangach, valyuta balansingizga qo‘shiladi.",
        reply_markup=_stars_keyboard(),
    )


async def _invoice(
    message: Message,
    product: str,
    quantity: int,
    title: str,
    description: str,
    stars: int,
) -> None:
    if message.from_user is None:
        return
    payload = f"stars:{product}:{quantity}:{message.from_user.id}"
    await message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=stars)],
    )


async def _buy_product(callback: CallbackQuery, product: str, quantity: int) -> None:
    if callback.message is None:
        await callback.answer("Xarid oynasini ochib bo‘lmadi.", show_alert=True)
        return
    if product == "coins":
        if quantity < 1 or quantity > MAX_COIN_PURCHASE:
            await callback.answer("Tanga miqdori 1–10000 oralig‘ida bo‘lsin.", show_alert=True)
            return
        await _invoice(callback.message, "coins", quantity, f"{quantity} tanga", f"Balansingizga {quantity} tanga qo‘shiladi.", quantity)
    elif product == "diamond":
        if quantity < 1 or quantity > 1000:
            await callback.answer("Olmos miqdori noto‘g‘ri.", show_alert=True)
            return
        await _invoice(callback.message, "diamond", quantity, f"{quantity} olmos", f"Balansingizga {quantity} olmos qo‘shiladi.", quantity * 2)
    elif product == "premium" and quantity == PREMIUM_DAYS:
        await _invoice(callback.message, "premium", PREMIUM_DAYS, "MafiaUzBot Premium", f"{PREMIUM_DAYS} kunlik Premium maqom va qo‘shimcha imtiyozlar.", PREMIUM_STARS)
    elif product == "battlepass" and quantity == 30:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        async with get_session_factory()() as session:
            already_owned = await session.get(BotSetting, f"u:{callback.from_user.id}:bp_premium:{month}")
        if already_owned and already_owned.value == "1":
            await callback.answer("Sizda bu mavsumning Premium Pass’i allaqachon bor.", show_alert=True)
            return
        await _invoice(callback.message, "battlepass", 30, "MafiaUzBot Premium Pass", "Joriy mavsum uchun Premium Battle Pass va maxsus mukofotlar.", 30)
    else:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    await callback.answer("To‘lov oynasi ochildi.")


@router.callback_query(F.data.startswith("stars:buy:"))
async def stars_buy_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Mahsulot ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    try:
        quantity = int(parts[3])
    except ValueError:
        await callback.answer("Miqdor noto‘g‘ri.", show_alert=True)
        return
    await _buy_product(callback, parts[2], quantity)


@router.message(Command("buycoins"))
async def buy_coins(message: Message, command: CommandObject) -> None:
    raw = command.args.strip() if command.args else "100"
    try:
        quantity = int(raw)
    except ValueError:
        await message.answer("Foydalanish: <code>/buycoins 100</code> — 100 tanga = 100 ⭐.")
        return
    if quantity < 1 or quantity > MAX_COIN_PURCHASE:
        await message.answer("1–10000 tanga oralig‘ini tanlang.")
        return
    await _invoice(message, "coins", quantity, f"{quantity} tanga", f"Balansingizga {quantity} tanga qo‘shiladi.", quantity)


@router.message(Command("buydiamond"))
async def buy_diamond(message: Message, command: CommandObject) -> None:
    raw = command.args.strip() if command.args else "1"
    try:
        quantity = int(raw)
    except ValueError:
        await message.answer("Foydalanish: <code>/buydiamond 1</code> — 1 olmos = 2 ⭐.")
        return
    if quantity < 1 or quantity > 1000:
        await message.answer("1–1000 olmos oralig‘ini tanlang.")
        return
    await _invoice(message, "diamond", quantity, f"{quantity} olmos", f"Balansingizga {quantity} olmos qo‘shiladi.", quantity * 2)


@router.message(Command("buyvip"))
@router.message(Command("buypremium"))
async def buy_premium(message: Message) -> None:
    await _invoice(
        message, "premium", PREMIUM_DAYS, "MafiaUzBot Premium",
        f"{PREMIUM_DAYS} kunlik Premium maqom va qo‘shimcha imtiyozlar.", PREMIUM_STARS,
    )


def _expected_stars(product: str, quantity: int) -> int | None:
    if product == "coins" and 1 <= quantity <= MAX_COIN_PURCHASE:
        return quantity
    if product == "diamond" and 1 <= quantity <= 1000:
        return quantity * 2
    if product == "premium" and quantity == PREMIUM_DAYS:
        return PREMIUM_STARS
    if product == "battlepass" and quantity == 30:
        return 30
    return None


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    parts = query.invoice_payload.split(":")
    valid = False
    if len(parts) == 4 and parts[0] == "stars" and parts[3].isdigit():
        try:
            quantity = int(parts[2])
            expected = _expected_stars(parts[1], quantity)
            valid = (
                query.currency == "XTR"
                and int(parts[3]) == query.from_user.id
                and expected is not None
                and query.total_amount == expected
            )
        except ValueError:
            valid = False
    await query.answer(
        ok=valid,
        error_message=None if valid else "To‘lov ma’lumotlari noto‘g‘ri. Qayta urinib ko‘ring.",
    )


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if not message.from_user or not payment:
        return

    parts = payment.invoice_payload.split(":")
    if len(parts) != 4 or parts[0] != "stars" or not parts[3].isdigit():
        return
    uid = message.from_user.id
    if int(parts[3]) != uid or payment.currency != "XTR":
        return
    try:
        quantity = int(parts[2])
    except ValueError:
        return
    expected = _expected_stars(parts[1], quantity)
    if expected is None or payment.total_amount != expected:
        await message.answer("⚠️ To‘lov ma’lumoti mos kelmadi. Yordam uchun administratorga yozing.")
        return

    charge_key = f"payment:charge:{payment.telegram_payment_charge_id}"
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as session:
        async with session.begin():
            if await session.get(BotSetting, charge_key):
                await message.answer("✅ Bu to‘lov oldin qayta ishlangan.")
                return

            session.add(BotSetting(key=charge_key, value=json.dumps({
                "user_id": uid,
                "payload": payment.invoice_payload,
                "amount": payment.total_amount,
                "paid_at": now.isoformat(),
            })))

            if parts[1] == "coins":
                key = f"u:{uid}:coins"
                row = await session.get(BotSetting, key)
                balance = int(row.value) if row else 100
                if row is None:
                    session.add(BotSetting(key=key, value=str(balance + quantity)))
                else:
                    row.value = str(balance + quantity)
                reply = f"🎉 Xarid muvaffaqiyatli! Balansingizga <b>+{quantity} 🪙</b> qo‘shildi."

            elif parts[1] == "diamond":
                key = f"u:{uid}:diamonds"
                row = await session.get(BotSetting, key)
                balance = int(row.value) if row else 0
                if row is None:
                    session.add(BotSetting(key=key, value=str(balance + quantity)))
                else:
                    row.value = str(balance + quantity)
                reply = f"💎 Xarid muvaffaqiyatli! Balansingizga <b>+{quantity} olmos</b> qo‘shildi."

            elif parts[1] == "battlepass":
                season = now.strftime("%Y-%m")
                key = f"u:{uid}:bp_premium:{season}"
                row = await session.get(BotSetting, key)
                if row is None:
                    session.add(BotSetting(key=key, value="1"))
                else:
                    row.value = "1"
                reply = (
                    "💎 <b>PREMIUM BATTLE PASS OCHILDI!</b>\n\n"
                    "🎟️ Joriy mavsumdagi Premium mukofotlar ochildi.\n"
                    "🎁 /battlepass orqali mukofotlarni ko‘ring."
                )
            else:
                key = f"u:{uid}:premium_until"
                row = await session.get(BotSetting, key)
                old_until = None
                if row:
                    try:
                        old_until = datetime.fromisoformat(row.value)
                        if old_until.tzinfo is None:
                            old_until = old_until.replace(tzinfo=timezone.utc)
                    except ValueError:
                        old_until = None
                base = old_until if old_until and old_until > now else now
                until = base + timedelta(days=PREMIUM_DAYS)
                if row is None:
                    session.add(BotSetting(key=key, value=until.isoformat()))
                else:
                    row.value = until.isoformat()
                reply = (
                    "👑 <b>PREMIUM FAOLLASHTIRILDI!</b>\n\n"
                    f"✨ Imtiyozlar {PREMIUM_DAYS} kun davomida faol.\n"
                    f"📅 Tugash vaqti: <code>{until.strftime('%Y-%m-%d %H:%M UTC')}</code>\n"
                    "🎁 G‘alabalar uchun 25% ko‘proq tanga olasiz."
                )

    await message.answer(reply, reply_markup=_stars_keyboard())
