from aiogram import F, Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

router = Router(name="inline")

BOT_URL = "https://t.me/MafiaJaneUzbot"
GROUP_URL = "https://t.me/MafiaJaneUzbot?startgroup=play"
APP_URL = "https://mafiauzbot-production.up.railway.app"


def _result(result_id: str, title: str, description: str, text: str, button_text: str, url: str):
    return InlineQueryResultArticle(
        id=result_id,
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=text,
            parse_mode="HTML",
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=url)]]
        ),
    )


@router.inline_query()
async def inline_handler(query: InlineQuery) -> None:
    search = (query.query or "").strip().lower()

    results = [
        _result(
            "mafia_invite",
            "🎭 Mafia o‘yiniga taklif",
            "Do‘stlaringizni MafiaUzBot o‘yiniga chaqiring",
            "🎭 <b>MAFIA UZ — O‘YINGA TAKLIF!</b>\n\n"
            "Do‘stlar bilan Mafia o‘ynaymiz! 👥\n"
            "Guruhga botni qo‘shing, guruhda /game yozing va kamida 4 kishi bo‘lib yig‘iling.\n\n"
            "🔐 Rollarni olish uchun har bir o‘yinchi botga shaxsiy chatda /start yuborsin.",
            "➕ Botni guruhga qo‘shish",
            GROUP_URL,
        ),
        _result(
            "mafia_rules",
            "📜 Mafia qoidalari",
            "O‘yin qanday o‘ynaladi?",
            "📜 <b>MAFIA UZ — QOIDALAR</b>\n\n"
            "🌙 Kechasi mafiya yashirin nishon tanlaydi.\n"
            "☀️ Kunduzi o‘yinchilar muhokama qiladi va ovoz beradi.\n"
            "🕵️ Maxsus rollar o‘z qobiliyatlaridan foydalanadi.\n"
            "🏆 Mafiya topilib yo‘q qilinsa, tinch aholi g‘alaba qiladi.\n\n"
            "Boshlash: botni guruhga qo‘shing va /game buyrug‘ini yuboring.",
            "🎮 Mini App’ni ochish",
            APP_URL,
        ),
        _result(
            "mafia_bot",
            "🤖 MafiaUzBot",
            "Botni ochish va o‘yinni boshlash",
            "🤖 <b>MafiaUzBot</b>\n\n"
            "👥 Guruhda /game — guruh o‘yini\n"
            "🤖 Mini App — Solo rejim va boshqa funksiyalar\n"
            "🔐 O‘yin rollarini olish uchun botga shaxsiy chatda /start yuboring.",
            "🤖 Botni ochish",
            BOT_URL,
        ),
    ]

    if search:
        words = search.split()
        filtered = [
            item for item in results
            if any(word in (item.title + " " + item.description).lower() for word in words)
        ]
        if filtered:
            results = filtered

    await query.answer(results, cache_time=10, is_personal=True)
