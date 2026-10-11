from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.keyboards import main_menu_keyboard
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
    "/app — MafiaUz Mini App\n"
    "/group — guruh uchun inline menyu\n"
    "/game — guruhda 90 soniyalik o‘yin ochish (kamida 4 kishi)\n"
    "/help — yordam\n"
    "/rules — o‘yin qoidalari\n"
    "/create — xona yaratish\n"
    "/join KOD — xona kodiga qo‘shilish\n"
    "/profile — profilingiz\n"
    "/leaderboard — reyting\n"
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
    if message.from_user is not None:
        user = message.from_user
        display_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
        async with get_session_factory()() as session:
            async with session.begin():
                await register_user(session, user.id, user.username, display_name or user.full_name)
    if command.args == "solo":
        await message.answer(
            "🤖 <b>SOLO GAME</b>\\n\\nO‘yinchilar sonini tanlang. O‘yin Mini App ichida ham mavjud.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 5 kishi", callback_data="solo:setup:5"),
                 InlineKeyboardButton(text="👥 7 kishi", callback_data="solo:setup:7")],
                [InlineKeyboardButton(text="👥 9 kishi", callback_data="solo:setup:9"),
                 InlineKeyboardButton(text="👥 12 kishi", callback_data="solo:setup:12")],
                [InlineKeyboardButton(text="✨ Mini App’da o‘ynash", web_app=WebAppInfo(url="https://mafiauzbot-production.up.railway.app"))],
            ]),
        )
        return
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    if message.chat.type == "private":
        app_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ MafiaUz Mini App’ni ochish", web_app=WebAppInfo(url="https://mafiauzbot-production.up.railway.app"))],
            [InlineKeyboardButton(text="👥 Botni guruhga qo‘shish", url="https://t.me/MafiaJaneUzbot?startgroup=play")],
        ])
    else:
        app_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Guruh menyusi", callback_data="group:menu")],
            [InlineKeyboardButton(text="➕ Botni boshqa guruhga qo‘shish", url="https://t.me/MafiaJaneUzbot?startgroup=play")],
        ])
    await message.answer("✨ <b>MafiaUz Mini App</b> — o‘yinlar, profil va Shop.", reply_markup=app_markup)


@router.message(Command("help"))
@router.message(lambda message: message.text == "🆘 Yordam")
async def help_handler(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("rules"))
@router.message(lambda message: message.text == "📜 Qoidalar")
async def rules_handler(message: Message) -> None:
    await message.answer(RULES_TEXT, reply_markup=main_menu_keyboard())
