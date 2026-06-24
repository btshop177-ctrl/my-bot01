import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, USE_PROXY, PROXY_URL
from database import db
from middlewares import JoinCheckMiddleware
from handlers import admin, user, group

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    if USE_PROXY:
        logger.info(f"🌐 Proxy: {PROXY_URL}")
        session = AiohttpSession(proxy=PROXY_URL)
    else:
        session = None

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    await db.connect()
    logger.info("✅ Database connected!")

    # میدلور فقط برای PV (گروه هندلر جداگانه داره)
    dp.message.middleware(JoinCheckMiddleware())
    dp.callback_query.middleware(JoinCheckMiddleware())

    # ترتیب مهم: admin → user → group
    dp.include_router(admin.router)
    dp.include_router(user.router)
    dp.include_router(group.router)

    logger.info("🚀 Bot starting...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()
        logger.info("Bot stopped!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user!")
