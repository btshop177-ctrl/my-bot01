"""
ماژول ساعت - مدیریت آپدیت نام و بیو
"""

import asyncio
from datetime import datetime
import pytz
from telethon.tl.functions.account import UpdateProfileRequest
from fonts import convert_time


class ClockManager:
    def __init__(self, client, config_manager):
        self.client = client
        self.config = config_manager
        self.running = False
        self.task = None
        self.last_time = ""
        self.last_bio = ""

    def get_fancy_time(self) -> str:
        """ساخت ساعت فنسی با فونت انتخابی"""
        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz)
        time_str = now.strftime("%H:%M")
        font_id = self.config.get("clock_font", 9)
        fancy = convert_time(time_str, font_id)
        return f"⌥ {fancy}"

    def get_bio_with_time(self) -> str:
        """ساخت متن بیو با ساعت"""
        bio_text = self.config.get("bio_text", "")
        if not bio_text:
            return ""

        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz)
        time_str = now.strftime("%H:%M")
        font_id = self.config.get("clock_font", 9)
        fancy = convert_time(time_str, font_id)
        return f"{bio_text} | {fancy}"

    async def clock_loop(self):
        """حلقه اصلی ساعت"""
        self.running = True
        print("🕐 ساعت روشن شد")

        while self.running:
            try:
                if self.config.get("clock_enabled"):
                    current_time = self.get_fancy_time()
                    if current_time != self.last_time:
                        await self.client(UpdateProfileRequest(
                            last_name=current_time
                        ))
                        self.last_time = current_time
                        print(f"⏰ Last Name: {current_time}")

                if self.config.get("clock_bio_enabled"):
                    full_bio = self.get_bio_with_time()
                    if full_bio and full_bio != self.last_bio:
                        await self.client(UpdateProfileRequest(
                            about=full_bio
                        ))
                        self.last_bio = full_bio
                        print(f"📝 Bio: {full_bio}")

                now = datetime.now()
                wait = 60 - now.second + 1
                await asyncio.sleep(wait)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Clock Error: {e}")
                await asyncio.sleep(10)

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.ensure_future(self.clock_loop())

    def stop(self):
        self.running = False
        if self.task and not self.task.done():
            self.task.cancel()
        self.last_time = ""
        self.last_bio = ""
        print("🕐 ساعت خاموش شد")