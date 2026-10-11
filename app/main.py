import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

from app.config import get_settings
from app.handlers.start import router as start_router
from app.handlers.rooms import router as rooms_router


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(rooms_router)

    @dispatcher.error()
    async def on_error(event: ErrorEvent) -> bool:
        logger.error(\n            "Telegram update handler failed",\n            exc_info=(type(event.exception), event.exception, event.exception.__traceback__),\n        )
        return True

    try:
        logger.info("MafiaUzBot polling started")
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        await bot.session.close()
        logger.info("MafiaUzBot polling stopped")
