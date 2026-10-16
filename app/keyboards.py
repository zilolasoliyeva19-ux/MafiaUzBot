from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 O‘yin o‘ynash"), KeyboardButton(text="🤖 Solo Game")],
            [KeyboardButton(text="🏠 Xona yaratish"), KeyboardButton(text="🚪 Xonaga qo‘shilish")],
            [KeyboardButton(text="👤 Profil"), KeyboardButton(text="🏆 Reyting")],
            [KeyboardButton(text="🎁 Kunlik sovg‘a"), KeyboardButton(text="🏅 Yutuqlar")],
            [KeyboardButton(text="🎟️ Battle Pass"), KeyboardButton(text="🌟 Mavsum")],
            [KeyboardButton(text="👥 Do‘stlar"), KeyboardButton(text="🛒 Shop")],
            [KeyboardButton(text="⭐ Stars / Premium"), KeyboardButton(text="⚙️ Sozlamalar")],
            [KeyboardButton(text="📜 Qoidalar"), KeyboardButton(text="🆘 Yordam")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Menyudan tanlang…",
    )
