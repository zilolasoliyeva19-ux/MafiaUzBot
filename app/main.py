import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    ErrorEvent,
)

from app.config import get_settings
from app.database import dispose_engine
from app.handlers.admin import router as admin_router
from app.handlers.features import router as features_router
from app.handlers.gameplay import router as gameplay_router
from app.handlers.inline import router as inline_router
from app.handlers.miniapp import router as miniapp_router
from app.handlers.payments import router as payments_router
from app.handlers.progression import router as progression_router
from app.handlers.rooms import router as rooms_router
from app.handlers.social import router as social_router
from app.handlers.start import router as start_router


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def start_web_server() -> ThreadingHTTPServer:
    class HealthHandler(SimpleHTTPRequestHandler):
        """Keep Railway's health endpoint while the optional Mini App is disabled."""

        def do_GET(self):
            if self.path in {"/health", "/healthz"}:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","service":"MafiaUzBot"}')
                return
            self.send_error(404, "Web App vaqtincha o‘chirilgan")

        def log_message(self, format, *args):
            logging.getLogger("health.http").info(format, *args)

    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="miniapp-http", daemon=True)
    thread.start()
    logging.getLogger(__name__).info("MafiaUzBot health endpoint listening on port %s; Mini App disabled", port)
    return server



async def configure_bot_commands(bot: Bot) -> None:
    """Set separate Telegram command menus for private chats and groups."""
    private_commands = [
        BotCommand(command="start", description="Asosiy menyu"),
        BotCommand(command="solo", description="Botlarga qarshi o‘ynash"),
        BotCommand(command="create", description="Yangi xona yaratish"),
        BotCommand(command="join", description="Xona kodiga qo‘shilish"),
        BotCommand(command="play", description="Ochiq xonalarni ko‘rish"),
        BotCommand(command="profile", description="Profil va statistika"),
        BotCommand(command="daily", description="Kunlik sovg‘a va topshiriqlar"),
        BotCommand(command="achievements", description="Yutuqlar va medallar"),
        BotCommand(command="battlepass", description="Mavsumiy Battle Pass"),
        BotCommand(command="season", description="Joriy mavsum reytingi"),
        BotCommand(command="leaderboard", description="O‘yinchilar reytingi"),
        BotCommand(command="shop", description="Do‘kon va inventar"),
        BotCommand(command="settings", description="Sozlamalar"),
        BotCommand(command="referral", description="Taklif havolasi"),
        BotCommand(command="lastwords", description="Oxirgi so‘zni yozish"),
        BotCommand(command="skip", description="Oxirgi so‘zdan voz kechish"),
        BotCommand(command="stars", description="Stars va Premium"),
        BotCommand(command="buycoins", description="Tangalar xarid qilish: /buycoins 100"),
        BotCommand(command="buydiamond", description="Olmos xarid qilish"),
        BotCommand(command="buypremium", description="Premium — 50 Stars / 30 kun"),
        BotCommand(command="rules", description="O‘yin qoidalari"),
        BotCommand(command="help", description="Yordam"),
    ]
    group_commands = [
        BotCommand(command="game", description="Guruhda o‘yin boshlash"),
        BotCommand(command="group", description="Guruh menyusi"),
        BotCommand(command="play", description="Ochiq xonalar"),
        BotCommand(command="create", description="Xona yaratish"),
        BotCommand(command="join", description="Xona kodiga qo‘shilish"),
        BotCommand(command="leave", description="Kutish xonasidan chiqish"),
        BotCommand(command="rules", description="O‘yin qoidalari"),
        BotCommand(command="help", description="Yordam"),
    ]
    await bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    web_server = start_web_server()

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await configure_bot_commands(bot)

    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(inline_router)
    dispatcher.include_router(miniapp_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(payments_router)
    dispatcher.include_router(progression_router)
    dispatcher.include_router(social_router)
    dispatcher.include_router(features_router)
    dispatcher.include_router(rooms_router)
    dispatcher.include_router(gameplay_router)

    @dispatcher.error()
    async def on_error(event: ErrorEvent) -> bool:
        exception = event.exception
        logger.error(
            "Telegram update handler failed",
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        return True

    try:
        logger.info("MafiaUzBot polling started")
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        web_server.shutdown()
        web_server.server_close()
        await bot.session.close()
        await dispose_engine()
        logger.info("MafiaUzBot polling stopped")
