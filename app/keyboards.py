from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 O‘yin o‘ynash"), KeyboardButton(text="🏠 Xona yaratish")],
            [KeyboardButton(text="🚪 Xonaga qo‘shilish"), KeyboardButton(text="👤 Profilim")],
            [KeyboardButton(text="🏆 Reyting"), KeyboardButton(text="📜 Qoidalar")],
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="🆘 Yordam")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Menyudan tanlang…",
    )
