import asyncio
import json
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from app.config import get_settings
from app.database import get_session_factory
from app.models import AdminAuditLog, BotSetting, GameMatch, GameRoom, User

router = Router(name="admin")


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats"),
            InlineKeyboardButton(text="🎮 Faol o‘yinlar", callback_data="admin:rooms"),
        ],
        [
            InlineKeyboardButton(text="🪙 Tangalar", callback_data="admin:coins"),
            InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="admin:broadcast"),
        ],
        [
            InlineKeyboardButton(text="🗳️ Ovoz tizimi", callback_data="admin:votes"),
            InlineKeyboardButton(text="🛡️ Anti-cheat", callback_data="admin:security"),
        ],
        [InlineKeyboardButton(text="👥 Barcha foydalanuvchilar", callback_data="admin:users:0")],
        [InlineKeyboardButton(text="❔ Qo‘llanma", callback_data="admin:help")],
        [InlineKeyboardButton(text="🔄 Panelni yangilash", callback_data="admin:home")],
    ])


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Bu bo‘lim faqat administratorlar uchun.")
        return
    await message.answer(
        "🛠️ <b>MAFIA UZ · ADMINISTRATOR PANELI</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>Bot boshqaruvi, statistika va xavfsizlik — barchasi bitta joyda.</blockquote>\n\n"
        "📊 <b>Statistika</b> — foydalanuvchilar va o‘yinlar\n"
        "🎮 <b>Faol o‘yinlar</b> — hozirgi xonalar\n"
        "🪙 <b>Iqtisod</b> — tangalarni boshqarish\n"
        "🛡️ <b>Xavfsizlik</b> — anti-cheat va audit\n\n"
        "<i>Bo‘limni tugma orqali tanlang. Muhim admin amallari audit jurnalida qayd etiladi.</i>",
        reply_markup=_keyboard(),
    )


@router.callback_query(F.data.startswith("admin:"))
async def admin_actions(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return
    action = (callback.data or "").split(":", 1)[1]

    if action.startswith("users"):
        parts = action.split(":")
        try:
            offset = max(0, int(parts[1])) if len(parts) > 1 else 0
        except ValueError:
            offset = 0
        async with get_session_factory()() as session:
            users = list((await session.scalars(
                select(User).order_by(User.registered_at.desc()).offset(offset).limit(10)
            )).all())
            total = await session.scalar(select(func.count()).select_from(User)) or 0
        rows = []
        for user in users:
            status = "⛔ BAN" if user.is_banned else "✅ faol"
            rows.append([InlineKeyboardButton(
                text=f"{status} · {user.display_name[:32]} · ID {user.telegram_id}",
                callback_data=f"admin:user:{user.telegram_id}",
            )])
        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin:users:{max(0, offset-10)}"))
        if offset + 10 < total:
            nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin:users:{offset+10}"))
        if nav:
            rows.append(nav)
        rows.append([InlineKeyboardButton(text="🏠 Admin bosh sahifa", callback_data="admin:home")])
        body = (
            "👥 <b>BARCHA FOYDALANUVCHILAR</b>\\n"
            "<blockquote>Username yashirilgan yoki o‘zgargan bo‘lsa ham, ro‘yxat bazadagi Telegram ID orqali ishlaydi.</blockquote>\\n\\n"
            f"Jami: <b>{total}</b> · Ko‘rsatilmoqda: <b>{min(offset+1, total) if total else 0}–{min(offset+len(users), total)}</b>\\n"
            "Foydalanuvchini tanlab, profil ma’lumotini va ban boshqaruvini oching."
        )
        await callback.answer()
        if callback.message:
            try:
                await callback.message.edit_text(body, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            except TelegramBadRequest:
                await callback.message.answer(body, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return

    if action.startswith("user:"):
        try:
            target_id = int(action.split(":")[1])
        except (IndexError, ValueError):
            await callback.answer("ID noto‘g‘ri.", show_alert=True)
            return
        async with get_session_factory()() as session:
            user = await session.get(User, target_id)
        if not user:
            await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        status = "⛔ Bloklangan" if user.is_banned else "🟢 Faol"
        toggle = InlineKeyboardButton(
            text="♻️ Blokdan chiqarish" if user.is_banned else "⛔ Barcha xizmatlardan bloklash",
            callback_data=f"admin:toggleban:{target_id}",
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [toggle],
            [InlineKeyboardButton(text="🪙 Balansni boshqarish", callback_data=f"admin:money:{target_id}")],
            [InlineKeyboardButton(text="⬅️ Foydalanuvchilar", callback_data="admin:users:0")],
            [InlineKeyboardButton(text="🏠 Admin bosh sahifa", callback_data="admin:home")],
        ])
        body = (
            "👤 <b>FOYDALANUVCHI KARTASI</b>\\n\\n"
            f"Ism: <b>{escape(user.display_name)}</b>\\n"
            f"Telegram ID: <code>{user.telegram_id}</code>\\n"
            f"Username: <code>{escape('@'+user.username) if user.username else 'yashirilgan / mavjud emas'}</code>\\n"
            f"Holat: <b>{status}</b>\\n"
            f"🎮 O‘yinlar: <b>{user.games_played}</b> · 🏆 G‘alaba: <b>{user.wins}</b>"
        )
        await callback.answer()
        if callback.message:
            try:
                await callback.message.edit_text(body, reply_markup=keyboard)
            except TelegramBadRequest:
                await callback.message.answer(body, reply_markup=keyboard)
        return

    if action.startswith("toggleban:"):
        try:
            target_id = int(action.split(":")[1])
        except (IndexError, ValueError):
            await callback.answer("ID noto‘g‘ri.", show_alert=True)
            return
        if target_id == callback.from_user.id:
            await callback.answer("O‘zingizni bloklay olmaysiz.", show_alert=True)
            return
        async with get_session_factory()() as session:
            async with session.begin():
                user = await session.get(User, target_id)
                if not user:
                    await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
                    return
                user.is_banned = not user.is_banned
                banned = user.is_banned
                session.add(AdminAuditLog(
                    admin_id=callback.from_user.id,
                    action="ban_user" if banned else "unban_user",
                    target_id=target_id,
                    details="Keyboard orqali boshqarildi",
                ))
        await callback.answer("Hisob bloklandi." if banned else "Hisob blokdan chiqarildi.", show_alert=True)
        if callback.message:
            try:
                await callback.message.edit_text(
                    f"{'⛔ Hisob bloklandi' if banned else '✅ Hisob blokdan chiqarildi'}\\nTelegram ID: <code>{target_id}</code>",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="⬅️ Foydalanuvchilar", callback_data="admin:users:0")],
                        [InlineKeyboardButton(text="🏠 Admin bosh sahifa", callback_data="admin:home")],
                    ]),
                )
            except TelegramBadRequest:
                pass
        try:
            await callback.bot.send_message(
                target_id,
                "⛔ Hisobingiz administrator tomonidan barcha bot xizmatlaridan bloklandi."
                if banned else "✅ Hisobingizdagi administrator bloklovi olib tashlandi.",
            )
        except Exception:
            pass
        return

    if action.startswith("money:"):
        parts = action.split(":")
        if len(parts) == 2:
            try:
                target_id = int(parts[1])
            except ValueError:
                await callback.answer("ID noto‘g‘ri.", show_alert=True)
                return
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🪙 Tanga qo‘shish", callback_data=f"admin:money:{target_id}:coins:add"),
                 InlineKeyboardButton(text="🪙 Tanga ayirish", callback_data=f"admin:money:{target_id}:coins:remove")],
                [InlineKeyboardButton(text="💎 Olmos qo‘shish", callback_data=f"admin:money:{target_id}:diamonds:add"),
                 InlineKeyboardButton(text="💎 Olmos ayirish", callback_data=f"admin:money:{target_id}:diamonds:remove")],
                [InlineKeyboardButton(text="⬅️ Foydalanuvchi", callback_data=f"admin:user:{target_id}")],
            ])
            await callback.answer()
            if callback.message:
                await callback.message.answer(
                    f"💰 <b>Balans boshqaruvi</b> · <code>{target_id}</code>\n"
                    "Avval valyuta va amalni tanlang, keyin miqdorni tanlang.",
                    reply_markup=keyboard,
                )
            return
        if len(parts) == 4:
            try:
                target_id = int(parts[1])
            except ValueError:
                await callback.answer("ID noto‘g‘ri.", show_alert=True)
                return
            currency, operation = parts[2], parts[3]
            if currency not in {"coins", "diamonds"} or operation not in {"add", "remove"}:
                await callback.answer("Amal noto‘g‘ri.", show_alert=True)
                return
            icon = "🪙" if currency == "coins" else "💎"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"10 {icon}", callback_data=f"admin:moneyset:{target_id}:{currency}:{operation}:10"),
                 InlineKeyboardButton(text=f"50 {icon}", callback_data=f"admin:moneyset:{target_id}:{currency}:{operation}:50")],
                [InlineKeyboardButton(text=f"100 {icon}", callback_data=f"admin:moneyset:{target_id}:{currency}:{operation}:100"),
                 InlineKeyboardButton(text=f"500 {icon}", callback_data=f"admin:moneyset:{target_id}:{currency}:{operation}:500")],
                [InlineKeyboardButton(text="⬅️ Balans menyusi", callback_data=f"admin:money:{target_id}")],
            ])
            await callback.answer()
            if callback.message:
                await callback.message.answer(
                    f"{'➕ Qo‘shish' if operation == 'add' else '➖ Ayirish'} · {icon}\n"
                    "Kerakli miqdorni tanlang:",
                    reply_markup=keyboard,
                )
            return
        await callback.answer("Balans amali noto‘g‘ri.", show_alert=True)
        return

    if action.startswith("moneyset:"):
        parts = action.split(":")
        try:
            target_id, amount = int(parts[1]), int(parts[4])
        except (IndexError, ValueError):
            await callback.answer("Miqdor noto‘g‘ri.", show_alert=True)
            return
        if len(parts) != 5:
            await callback.answer("Amal noto‘g‘ri.", show_alert=True)
            return
        currency, operation = parts[2], parts[3]
        if currency not in {"coins", "diamonds"} or operation not in {"add", "remove"} or amount not in {10, 50, 100, 500}:
            await callback.answer("Amal noto‘g‘ri.", show_alert=True)
            return
        key = f"u:{target_id}:{currency}"
        async with get_session_factory()() as session:
            async with session.begin():
                user = await session.get(User, target_id)
                if not user:
                    await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
                    return
                row = await session.get(BotSetting, key)
                default = 100 if currency == "coins" else 0
                old = int(row.value) if row else default
                new = old + amount if operation == "add" else max(0, old - amount)
                if row is None:
                    session.add(BotSetting(key=key, value=str(new)))
                else:
                    row.value = str(new)
                session.add(AdminAuditLog(
                    admin_id=callback.from_user.id,
                    action=f"adjust_{currency}",
                    target_id=target_id,
                    details=f"{operation} {amount}: {old}->{new}",
                ))
        icon = "🪙" if currency == "coins" else "💎"
        await callback.answer("Balans yangilandi.", show_alert=True)
        if callback.message:
            await callback.message.answer(
                f"✅ <code>{target_id}</code> balans yangilandi: <b>{new} {icon}</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Balans menyusi", callback_data=f"admin:money:{target_id}")],
                    [InlineKeyboardButton(text="👤 Foydalanuvchi", callback_data=f"admin:user:{target_id}")],
                ]),
            )
        return

    if action == "home":
        await callback.answer("Bosh sahifa ochildi.")
        if callback.message:
            try:
                await callback.message.edit_text(
                    "🛠️ <b>MAFIA UZ · ADMINISTRATOR PANELI</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "<blockquote>Bot boshqaruvi, statistika va xavfsizlik — barchasi bitta joyda.</blockquote>\n\n"
                    "📊 <b>Statistika</b> — foydalanuvchilar va o‘yinlar\n"
                    "🎮 <b>Faol o‘yinlar</b> — hozirgi xonalar\n"
                    "🪙 <b>Iqtisod</b> — tangalarni boshqarish\n"
                    "🛡️ <b>Xavfsizlik</b> — anti-cheat va audit\n\n"
                    "<i>Bo‘limni tugma orqali tanlang. Muhim admin amallari audit jurnalida qayd etiladi.</i>",
                    reply_markup=_keyboard(),
                )
            except TelegramBadRequest:
                pass
        return

    if action == "stats":
        async with get_session_factory()() as session:
            users = await session.scalar(select(func.count()).select_from(User)) or 0
            rooms = await session.scalar(select(func.count()).select_from(GameRoom)) or 0
            active_rooms = await session.scalar(select(func.count()).select_from(GameRoom).where(GameRoom.status == "active")) or 0
            matches = await session.scalar(select(func.count()).select_from(GameMatch)) or 0
            wins = await session.scalar(select(func.sum(User.wins))) or 0
        body = (
            f"📊 <b>Bot statistikasi</b>\n\n👥 Foydalanuvchilar: <b>{users}</b>\n"
            f"🏠 Jami xonalar: <b>{rooms}</b>\n🎮 Faol xonalar: <b>{active_rooms}</b>\n"
            f"🎲 Jami matchlar: <b>{matches}</b>\n🏆 Jami g‘alabalar: <b>{wins}</b>"
        )
    elif action == "rooms":
        async with get_session_factory()() as session:
            active_rooms = list((await session.scalars(
                select(GameRoom).where(GameRoom.status == "active").order_by(GameRoom.id.desc()).limit(10)
            )).all())
        body = "🎮 <b>Faol o‘yinlar</b>\n\n"
        body += "\n".join(
            f"• Xona <code>{room.room_code}</code> — egasi <code>{room.owner_id}</code>"
            for room in active_rooms
        ) if active_rooms else "Hozir faol xona yo‘q."
    elif action == "coins":
        body = (
            "🪙 <b>Tangalarni boshqarish</b>\n\n"
            "Foydalanuvchiga tanga qo‘shish uchun:\n"
            "<code>/coins TELEGRAM_ID MIQDOR</code>\n\n"
            "Masalan: <code>/coins 123456789 50</code> — 50 tanga qo‘shadi.\n"
            "Ayirish uchun manfiy miqdor yozing: <code>/coins 123456789 -20</code>."
        )
    elif action == "broadcast":
        body = (
            "📣 <b>Umumiy xabar yuborish</b>\n\n"
            "<code>/broadcast Xabar matni</code>\n\n"
            "Xabar foydalanuvchilarga rasmiy bot xabari sifatida yuboriladi. "
            "Ko‘p foydalanuvchiga yuborishda Telegram cheklovlariga rioya qilinadi."
        )
    elif action == "votes":
        body = (
            "🗳️ <b>Ovoz berish tizimi</b>\n\n"
            "Solo rejimida bot-o‘yinchilar navbatma-navbat ovoz bildiradi. "
            "Eng ko‘p ovoz olgan nomzod sudga chiqadi. Like Dislike’dan ko‘p bo‘lsa osiladi; "
            "tenglikda yoki Dislike ko‘p bo‘lsa ozod qilinadi.\n\n"
            "Ovozlar sun’iy ravishda haqiqiy foydalanuvchilar ovozi sifatida ko‘rsatilmaydi."
        )
    elif action == "security":
        async with get_session_factory()() as session:
            banned = list((await session.scalars(
                select(User).where(User.is_banned.is_(True)).order_by(User.telegram_id).limit(20)
            )).all())
            recent = list((await session.scalars(
                select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(5)
            )).all())
        banned_lines = "\n".join(
            f"• <code>{user.telegram_id}</code> — {escape(user.display_name)}"
            for user in banned
        )
        audit_lines = "\n".join(
            f"• {escape(row.action)} · <code>{row.target_id or '—'}</code>"
            for row in recent
        )
        body = (
            "🛡️ <b>ANTI-CHEAT / XAVFSIZLIK</b>\n\n"
            "✅ Takroriy ovoz va tungi amal server tomonidan rad etiladi.\n"
            "✅ Faqat tirik o‘yinchi, to‘g‘ri rol va to‘g‘ri bosqich amal bajarishi mumkin.\n"
            "✅ Bloklangan hisoblar barcha xabar va callbacklarda tekshiriladi.\n\n"
            f"⛔ Bloklangan hisoblar: <b>{len(banned)}</b>\n"
            + (banned_lines or "Hozir bloklangan hisob yo‘q.") +
            "\n\n<b>Oxirgi admin amallari:</b>\n" + (audit_lines or "Audit jurnali bo‘sh.") +
            "\n\nBloklash: <code>/ban TELEGRAM_ID</code> · Ochish: <code>/unban TELEGRAM_ID</code>"
        )
    elif action == "help":
        body = (
            "🧾 <b>ADMIN BUYRUQLARI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<code>/admin</code> — boshqaruv paneli\n"
            "<code>/broadcast MATN</code> — xabar yuborish\n"
            "<code>/coins ID MIQDOR</code> — balansni o‘zgartirish\n"
            "<code>/ban ID</code> — hisobni bloklash\n"
            "<code>/unban ID</code> — blokdan chiqarish\n\n"
            "<i>Har bir muhim boshqaruv amali audit jurnaliga yoziladi.</i>"
        )
    else:
        await callback.answer("Noma’lum amal.", show_alert=True)
        return

    body = "🛠️ <b>MAFIA UZ · ADMINISTRATOR</b>\n━━━━━━━━━━━━━━━━━━\n\n" + body
    await callback.answer()
    if callback.message:
        try:
            await callback.message.edit_text(body, reply_markup=_keyboard())
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                await callback.message.answer(body, reply_markup=_keyboard())


@router.message(Command("coins"))
async def admin_coins(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Foydalanish: <code>/coins TELEGRAM_ID MIQDOR</code>")
        return
    try:
        target_id, delta = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("ID va miqdor butun son bo‘lishi kerak.")
        return
    async with get_session_factory()() as session:
        async with session.begin():
            user = await session.get(User, target_id)
            if not user:
                await message.answer("Foydalanuvchi topilmadi.")
                return
            key = f"u:{target_id}:coins"
            row = await session.get(BotSetting, key)
            old = int(row.value) if row else 100
            new = max(0, old + delta)
            if row is None:
                session.add(BotSetting(key=key, value=str(new)))
            else:
                row.value = str(new)
            session.add(AdminAuditLog(
                admin_id=message.from_user.id, action="adjust_coins",
                target_id=target_id, details=f"{old}->{new}"
            ))
    await message.answer(f"✅ <code>{target_id}</code> balans: <b>{new} 🪙</b>", reply_markup=_keyboard())


@router.message(Command("broadcast"))
async def admin_broadcast(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return
    body = (message.text or "").partition(" ")[2].strip()
    if not body:
        await message.answer("Foydalanish: <code>/broadcast Xabar matni</code>")
        return
    async with get_session_factory()() as session:
        ids = list((await session.scalars(select(User.telegram_id))).all())
    sent = failed = 0
    for user_id in ids:
        try:
            await message.bot.send_message(user_id, body)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.06)
    async with get_session_factory()() as session:
        async with session.begin():
            session.add(AdminAuditLog(
                admin_id=message.from_user.id, action="broadcast",
                details=json.dumps({"sent": sent, "failed": failed}, ensure_ascii=False)
            ))
    await message.answer(
        f"📣 Yuborish yakunlandi. Yetkazildi: <b>{sent}</b>, xato: <b>{failed}</b>.",
        reply_markup=_keyboard(),
    )


@router.message(Command("ban"))
async def admin_ban(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return
    try:
        target_id = int((message.text or "").split()[1])
    except (IndexError, ValueError):
        await message.answer("Foydalanish: <code>/ban TELEGRAM_ID</code>")
        return
    if target_id == message.from_user.id:
        await message.answer("O‘zingizni bloklay olmaysiz.")
        return
    async with get_session_factory()() as session:
        async with session.begin():
            user = await session.get(User, target_id)
            if not user:
                await message.answer("Foydalanuvchi topilmadi. U botga avval /start yuborgan bo‘lishi kerak.")
                return
            user.is_banned = True
            session.add(AdminAuditLog(admin_id=message.from_user.id, action="ban_user", target_id=target_id, details="Admin ban"))
    await message.answer(f"⛔ <code>{target_id}</code> bloklandi.", reply_markup=_keyboard())


@router.message(Command("unban"))
async def admin_unban(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return
    try:
        target_id = int((message.text or "").split()[1])
    except (IndexError, ValueError):
        await message.answer("Foydalanish: <code>/unban TELEGRAM_ID</code>")
        return
    async with get_session_factory()() as session:
        async with session.begin():
            user = await session.get(User, target_id)
            if not user:
                await message.answer("Foydalanuvchi topilmadi.")
                return
            user.is_banned = False
            session.add(AdminAuditLog(admin_id=message.from_user.id, action="unban_user", target_id=target_id, details="Admin unban"))
    await message.answer(f"✅ <code>{target_id}</code> blokdan chiqarildi.", reply_markup=_keyboard())
