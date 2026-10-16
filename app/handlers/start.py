from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
import json

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.keyboards import main_menu_keyboard
from app.models import BotSetting, User
from app.database import get_session_factory
from app.services.rooms import register_user

router = Router(name="start")


WELCOME_TEXT = (
    "🎭 <b>MafiaUzBot</b> ga xush kelibsiz!\n\n"
    "👥 Do‘stlar bilan multiplayer xona yarating yoki 🤖 Solo Game rejimida botlarga qarshi o‘ynang.\n"
    "👤 Profilingizni ko‘ring, 🏆 reytingda ko‘tariling va 🛒 shopdan buyumlar oling.\n\n"
    "Boshlash uchun menyudan tanlang."
)

HELP_TEXT = (
    "🆘 <b>Yordam</b>\n\n"
    "/start — asosiy menyu\n"
    "/group — guruh menyusi\n"
    "Inline rejim — istalgan chatda @MafiaJaneUzbot deb yozing\n"
    "/game — guruhda 90 soniyalik o‘yin ochish (kamida 4 kishi)\n"
    "/help — yordam\n"
    "/rules — o‘yin qoidalari\n"
    "/create — xona yaratish\n"
    "/join KOD — xona kodiga qo‘shilish\n"
    "/profile — profilingiz va XP\n"
    "/leaderboard — reyting\n"
    "/daily — kunlik sovg‘a va topshiriqlar\n"
    "/achievements — yutuqlar\n"
    "/battlepass — mavsumiy mukofotlar\n"
    "/season — joriy mavsum reytingi\n"
    "/friends — do‘stlar ro‘yxati\n"
    "/friendadd @username — do‘stlik so‘rovi\n"
    "/referral — shaxsiy taklif havolangiz\n"
    "/solo — botlarga qarshi o‘ynash\n"
    "/shop — shop\n"
    "/settings — sozlamalar\n"
    "/leave — kutish xonasidan chiqish"
)

RULES_TEXT = (
    "📜 <b>Mafia — asosiy qoidalar</b>\n\n"
    "• O‘yinchilar maxfiy rollar oladi.\n"
    "• Tinch aholi muhokama va ovoz berish orqali mafiyani topadi.\n"
    "• Kechasi mafiya yashirin nishon tanlaydi; maxsus rollar o‘z qobiliyatidan foydalanadi.\n"
    "• Tirik o‘yinchilar kunduzgi ovoz berishda qatnashadi.\n"
    "• Barcha mafiya yo‘q qilinsa, tinch aholi g‘alaba qiladi.\n"
    "• Mafiya qarshi jamoa bilan tenglashsa yoki ustunlikka erishsa, mafiya g‘alaba qiladi.\n\n"
    "Multiplayer xonalar va Solo Game menyularidan foydalaning."
)


@router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject) -> None:
    referral_reward_to: int | None = None
    if message.from_user is not None:
        user = message.from_user
        display_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
        async with get_session_factory()() as session:
            async with session.begin():
                await register_user(session, user.id, user.username, display_name or user.full_name)
                # Reward only the first valid referral from a different registered user.
                if command.args and command.args.startswith("ref_"):
                    try:
                        referrer_id = int(command.args[4:])
                    except ValueError:
                        referrer_id = 0
                    if referrer_id and referrer_id != user.id:
                        referrer = await session.get(User, referrer_id)
                        attribution_key = f"u:{user.id}:referred_by"
                        attribution = await session.get(BotSetting, attribution_key)
                        if referrer is not None and attribution is None:
                            session.add(BotSetting(key=attribution_key, value=str(referrer_id)))
                            referrals_key = f"u:{referrer_id}:referrals"
                            referrals_setting = await session.get(BotSetting, referrals_key)
                            try:
                                referrals = json.loads(referrals_setting.value) if referrals_setting else []
                            except (ValueError, TypeError):
                                referrals = []
                            if user.id not in referrals:
                                referrals.append(user.id)
                            value = json.dumps(referrals)
                            if referrals_setting is None:
                                session.add(BotSetting(key=referrals_key, value=value))
                            else:
                                referrals_setting.value = value

                            coins_key = f"u:{referrer_id}:coins"
                            coins_setting = await session.get(BotSetting, coins_key)
                            current_coins = int(coins_setting.value) if coins_setting else 100
                            if coins_setting is None:
                                session.add(BotSetting(key=coins_key, value=str(current_coins + 5)))
                            else:
                                coins_setting.value = str(current_coins + 5)
                            referral_reward_to = referrer_id
    if referral_reward_to is not None:
        try:
            await message.bot.send_message(
                referral_reward_to,
                "🎉 <b>Referral mukofoti!</b>\nDo‘stingiz MafiaUzBot’ga taklif havolangiz orqali qo‘shildi. Balansingizga <b>+5 🪙</b> qo‘shildi.",
            )
        except Exception:
            pass

    if command.args == "solo":
        await message.answer(
            "🤖 <b>SOLO GAME</b>\n\nO‘yinchilar sonini tanlang. Telegram tugmalari orqali boshqariladi.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 5 kishi", callback_data="solo:setup:5"),
                 InlineKeyboardButton(text="👥 7 kishi", callback_data="solo:setup:7")],
                [InlineKeyboardButton(text="👥 9 kishi", callback_data="solo:setup:9"),
                 InlineKeyboardButton(text="👥 12 kishi", callback_data="solo:setup:12")],
            ]),
        )
        return
    if message.chat.type == "private":
        await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    else:
        await message.answer(WELCOME_TEXT)
    if message.chat.type == "private":
        menu_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Taklif havolam", callback_data="start:referral")],
            [InlineKeyboardButton(text="👥 Botni guruhga qo‘shish", url="https://t.me/MafiaJaneUzbot?startgroup=play")],
        ])
        await message.answer("✨ <b>Tezkor menyu</b>\nKerakli bo‘limni tanlang yoki pastdagi buyruqlar menyusidan foydalaning.", reply_markup=menu_markup)
    else:
        menu_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Guruh menyusi", callback_data="group:menu")],
            [InlineKeyboardButton(text="➕ Botni boshqa guruhga qo‘shish", url="https://t.me/MafiaJaneUzbot?startgroup=play")],
        ])
        await message.answer("🎭 <b>Guruh boshqaruvi</b>\nO‘yinni boshlash uchun /game yuboring yoki guruh menyusini oching.", reply_markup=menu_markup)


@router.message(Command("help"))
@router.message(lambda message: message.text == "🆘 Yordam")
async def help_handler(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("rules"))
@router.message(lambda message: message.text == "📜 Qoidalar")
async def rules_handler(message: Message) -> None:
    await message.answer(RULES_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(lambda callback: callback.data == "start:referral")
async def referral_callback(callback) -> None:
    if callback.message is not None:
        await referral_handler(callback.message)
    await callback.answer()


@router.message(Command("referral"))
async def referral_handler(message: Message) -> None:
    if message.from_user is None:
        return
    referral_url = f"https://t.me/MafiaJaneUzbot?start=ref_{message.from_user.id}"
    async with get_session_factory()() as session:
        setting = await session.get(BotSetting, f"u:{message.from_user.id}:referrals")
        try:
            referral_count = len(json.loads(setting.value)) if setting else 0
        except (ValueError, TypeError):
            referral_count = 0
    await message.answer(
        "🔗 <b>Sizning shaxsiy taklif havolangiz</b>\n\n"
        f"👥 Taklif orqali kelgan foydalanuvchilar: <b>{referral_count}</b>\n"
        "🎁 Har bir yangi foydalanuvchi birinchi marta shu havola orqali kirsa, sizga <b>+5 🪙</b> beriladi.\n\n"
        "Havolani do‘stlaringizga yuboring:\n"
        f"<code>{referral_url}</code>\n\n"
        "📤 Mukofot bir foydalanuvchi uchun faqat bir marta beriladi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Botni ochish", url=referral_url)],
            [InlineKeyboardButton(text="👥 Guruhga qo‘shish", url="https://t.me/MafiaJaneUzbot?startgroup=play")],
        ]),
    )
