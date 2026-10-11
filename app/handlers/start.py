from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.keyboards import main_menu_keyboard
from app.database import SessionFactory
from app.services.rooms import register_user

router = Router(name="start")


WELCOME_TEXT = (
    "🎭 <b>Mafia O‘yini</b> ga xush kelibsiz!\n\n"
    "Do‘stlaringiz bilan xona yarating, maxfiy rol oling va jamoangiz "
    "bilan g‘alaba qozoning.\n\n"
    "Boshlash uchun quyidagi menyudan foydalaning."
)

HELP_TEXT = (
    "🆘 <b>Yordam</b>\n\n"
    "/start — asosiy menyu\n"
    "/help — yordam\n"
    "/rules — o‘yin qoidalari\n"
    "/create — xona yaratish\n"
    "/join KOD — xona kodiga qo‘shilish\n"
    "/profile — profilingiz\n"
    "/leaderboard — reyting\n"
    "/leave — kutish xonasidan chiqish\n\n"
    "Xona va o‘yin funksiyalari bosqichma-bosqich qo‘shilmoqda."
)

RULES_TEXT = (
    "📜 <b>Mafia — asosiy qoidalar</b>\n\n"
    "• O‘yin boshlanganda har bir ishtirokchiga maxfiy rol beriladi.\n"
    "• Tinch aholi muhokama va ovoz berish orqali mafiyani topadi.\n"
    "• Kechasi mafiya yashirin nishon tanlaydi; maxsus rollar o‘z qobiliyatidan foydalanadi.\n"
    "• Tirik o‘yinchilar kunduzgi ovoz berishda qatnashadi.\n"
    "• Barcha mafiya yo‘q qilinsa, tinch aholi g‘alaba qiladi.\n"
    "• Mafiya qarshi jamoa bilan tenglashsa yoki ustunlikka erishsa, mafiya g‘alaba qiladi.\n\n"
    "Xona sozlamalarida qo‘shimcha rollar va taymerlar belgilanadi."
)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    if message.from_user is not None:
        user = message.from_user
        display_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
        async with SessionFactory() as session:
            async with session.begin():
                await register_user(
                    session,
                    user.id,
                    user.username,
                    display_name or user.full_name,
                )
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
@router.message(lambda message: message.text == "🆘 Yordam")
async def help_handler(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("rules"))
@router.message(lambda message: message.text == "📜 Qoidalar")
async def rules_handler(message: Message) -> None:
    await message.answer(RULES_TEXT, reply_markup=main_menu_keyboard())


@router.message(lambda message: message.text in {"⚙️ Sozlamalar", "👤 Profilim", "🏆 Reyting"})
async def planned_feature_handler(message: Message) -> None:
    labels = {
        "⚙️ Sozlamalar": "Sozlamalar",
        "👤 Profilim": "Profil",
        "🏆 Reyting": "Reyting",
    }
    feature = labels.get(message.text or "", "Funksiya")
    await message.answer(
        f"🛠 {feature} bo‘limi keyingi ishlab chiqish bosqichida qo‘shiladi.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("profile"))
@router.message(Command("leaderboard"))
async def upcoming_gameplay_handler(message: Message) -> None:
    await message.answer(
        "🚧 Bu funksiya hali ishlab chiqilmoqda. Hozircha menyu, yordam va qoidalar bo‘limlari ishlaydi. "
        "Xona va o‘yin mexanikasi keyingi bosqichda qo‘shiladi.",
        reply_markup=main_menu_keyboard(),
    )
