from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 O‘yin o‘ynash"), KeyboardButton(text="🤖 Solo Game")],
            [KeyboardButton(text="🏠 Xona yaratish"), KeyboardButton(text="🚪 Xonaga qo‘shilish")],
            [KeyboardButton(text="👤 Profil"), KeyboardButton(text="🏆 Reyting")],
            [KeyboardButton(text="🛒 Shop"), KeyboardButton(text="⚙️ Sozlamalar")],
            [KeyboardButton(text="📜 Qoidalar"), KeyboardButton(text="🆘 Yordam")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Menyudan tanlang…",
    )
