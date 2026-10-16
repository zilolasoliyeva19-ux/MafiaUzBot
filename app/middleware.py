from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.config import get_settings
from app.database import get_session_factory
from app.models import User


class BanGuardMiddleware(BaseMiddleware):
    """Reject updates from banned accounts before any game or economy handler runs."""

    async def __call__(self, handler, event, data):
        tg_user = data.get("event_from_user")
        if tg_user and tg_user.id not in get_settings().admin_ids:
            async with get_session_factory()() as session:
                user = await session.get(User, tg_user.id)
                banned = bool(user and user.is_banned)
            if banned:
                if isinstance(event, Message):
                    await event.answer("⛔ Hisobingiz administrator tomonidan bloklangan.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔ Hisobingiz bloklangan.", show_alert=True)
                return None
        return await handler(event, data)
