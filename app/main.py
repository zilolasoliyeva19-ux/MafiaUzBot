import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

from app.config import get_settings
from app.database import dispose_engine
from app.handlers.admin import router as admin_router
from app.handlers.features import router as features_router
from app.handlers.gameplay import router as gameplay_router
from app.handlers.inline import router as inline_router
from app.handlers.miniapp import router as miniapp_router
from app.handlers.payments import router as payments_router
from app.handlers.rooms import router as rooms_router
from app.handlers.social import router as social_router
from app.handlers.start import router as start_router


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def start_web_server() -> ThreadingHTTPServer:
    web_root = Path(__file__).resolve().parent.parent / "webapp"

    class MiniAppHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def do_GET(self):
            if self.path in {"/health", "/healthz"}:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","service":"MafiaUzBot"}')
                return
            if self.path == "/":
                self.path = "/index.html"
            return super().do_GET()

        def log_message(self, format, *args):
            logging.getLogger("miniapp.http").info(format, *args)

    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), MiniAppHandler)
    thread = threading.Thread(target=server.serve_forever, name="miniapp-http", daemon=True)
    thread.start()
    logging.getLogger(__name__).info("MafiaUz Mini App web server listening on port %s", port)
    return server


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    web_server = start_web_server()

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(inline_router)
    dispatcher.include_router(miniapp_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(payments_router)
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
