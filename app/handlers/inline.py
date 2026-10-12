from aiogram import Router
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
    user_id = query.from_user.id
    referral_url = f"{BOT_URL}?start=ref_{user_id}"

    results = [
        _result(
            "mafia_invite",
            "🎭 Mafia o‘yiniga taklif",
            "Do‘stlaringizni MafiaUzBot o‘yiniga chaqiring",
            "🎭 <b>MAFIA UZ — O‘YINGA TAKLIF!</b>\n\n"
            "Do‘stlar bilan <b>Mafia</b> o‘ynaymiz! 👥\n"
            "Guruhga botni qo‘shing, guruhda <code>/game</code> yozing va kamida 4 kishi bo‘lib yig‘iling.\n\n"
            "🔐 Rollarni olish uchun har bir o‘yinchi botning shaxsiy chatida <code>/start</code> yuborsin.",
            "➕ Botni guruhga qo‘shish",
            GROUP_URL,
        ),
        _result(
            "mafia_referral",
            "🔗 Shaxsiy taklif havolam",
            "Do‘stlaringizni taklif qilish uchun referral link",
            "🔗 <b>MAFIA UZ — DO‘STINGNI TAKLIF QIL!</b>\n\n"
            "Mening havolam orqali <b>MafiaUzBot</b>ni och: \n"
            f"{referral_url}\n\n"
            "👥 Do‘stlaringni taklif qil va birga o‘yna!",
            "🤖 Havolani ochish",
            referral_url,
        ),
        _result(
            "mafia_formatting",
            "✨ Matn formatlari",
            "Qalin, kursiv, tagiga chizish, iqtibos, kod va havola",
            "✨ <b>TELEGRAM MATN FORMATLARI</b>\n\n"
            "<b>Qalin matn</b> — muhim so‘zlar\n"
            "<i>Kursiv matn</i> — urg‘u berish\n"
            "<u>Tagiga chizilgan</u>\n"
            "<s>Ustidan chizilgan</s>\n"
            "<tg-spoiler>Spoiler matn</tg-spoiler>\n"
            "<blockquote>Bu iqtibos (quote) matni.</blockquote>\n"
            "<code>inline_code()</code>\n"
            "<pre>Bu kod bloki</pre>\n"
            '<a href="https://t.me/MafiaJaneUzbot">Bosiladigan havola</a>\n\n'
            "ℹ️ Bu namunalar Telegram HTML formatlashidan foydalanadi.",
            "🤖 MafiaUzBot",
            BOT_URL,
        ),
        _result(
            "mafia_rules",
            "📜 Mafia qoidalari",
            "O‘yin qanday o‘ynaladi?",
            "📜 <b>MAFIA UZ — QOIDALAR</b>\n\n"
            "🌙 Kechasi mafiya yashirin nishon tanlaydi.\n"
            "☀️ Kunduzi o‘yinchilar muhokama qiladi va ovoz beradi.\n"
            "🕵️ Maxsus rollar o‘z qobiliyatlaridan foydalanadi.\n"
            "🏆 Mafiya yo‘q qilinsa, tinch aholi g‘alaba qiladi.\n\n"
            "Boshlash uchun botni guruhga qo‘shing va <code>/game</code> buyrug‘ini yuboring.",
            "🎮 Mini App’ni ochish",
            APP_URL,
        ),
        _result(
            "mafia_bot",
            "🤖 MafiaUzBot",
            "Botni ochish va o‘yinni boshlash",
            "🤖 <b>MafiaUzBot</b>\n\n"
            "👥 Guruhda <code>/game</code> — guruh o‘yini\n"
            "🤖 Mini App — Solo rejim va boshqa funksiyalar\n"
            "🔐 Rollarni olish uchun botga shaxsiy chatda <code>/start</code> yuboring.",
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
