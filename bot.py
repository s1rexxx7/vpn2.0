import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands

from app.config import get_settings
from app.database import create_engine_and_session, init_db
from app.handlers import get_router
from app.services import SubscriptionService
from app.web import create_web_app


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    force=True,
)


async def main():
    settings = get_settings()

    engine, session_maker = create_engine_and_session(settings.DATABASE_URL)
    await init_db(engine)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
        ]
    )

    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    service = SubscriptionService(
        settings=settings,
        session_maker=session_maker,
        bot=bot,
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(get_router(service))

    web_app = create_web_app(service)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.APP_HOST, settings.APP_PORT)
    await site.start()

    logging.info(
        "HTTP server started on %s:%s",
        settings.APP_HOST,
        settings.APP_PORT,
    )
    logging.info(
        "YooKassa webhook URL: %s%s",
        settings.APP_BASE_URL,
        settings.YOOKASSA_WEBHOOK_PATH,
    )

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
        ]
    )
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())