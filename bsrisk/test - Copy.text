import asyncio

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

async def main():
    session = AiohttpSession(
        proxy="socks5://127.0.0.1:10808"
    )

    bot = Bot(
        token=TOKEN,
        session=session
    )

    me = await bot.get_me()
    print(me)

    await bot.session.close()

asyncio.run(main())