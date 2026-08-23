import asyncio
import os
import random
import re
import logging
import aiohttp
import json
import time
import collections
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, Timeout
from pyrogram.handlers import MessageHandler, EditedMessageHandler
from typing import Dict
import importlib
import gc
import psutil
from dotenv import load_dotenv
import sys

# تلاش برای ایمپورت profit
try:
    import profit
except ImportError:
    profit = None

load_dotenv()
# silent account
# ======================= تنظیمات اصلی =======================
API_ID = "29511262"
API_HASH = "c0da1e019c1d69a9abdae20941d923b4"
PHONE_NUMBER = "+989963308164"
BOT_USERNAME = "BslifeBot"
CHANNEL = "BSlifeChat"

DUPLICATE_WINDOW = 10  # ثانیه
MIN_DELAY_AFTER_ACTION = 1.5  # حداقل وقفه بعد از ارسال/کلیک
MAX_DELAY_AFTER_ACTION = 2.0  # حداکثر وقفه بعد از ارسال/کلیک

MAX_QUEUE_SIZE = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sniper.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

# ======================= وضعیت جهانی =======================
item_shop: dict = {}
item_queue = collections.deque()
queue_lock = asyncio.Lock()

last_processed: Dict[str, float] = {}
last_action_time = 0.0  # زمان آخرین عملیات (کلیک یا ارسال)
action_lock = asyncio.Lock()

stats = {"received": 0, "queued": 0, "sent": 0, "clicked": 0, "timeouts": 0}

# ======================= پترن‌ها =======================
PATTERN_SELL = re.compile(
    r"(s\d+):\s*(.+?)\s*x\s*(\d+)\s*->\s*([0-9\.,]+ ?[kKmM]?)",
    re.UNICODE | re.IGNORECASE
)


def parse_price(text: str) -> int:
    text = text.strip().lower().replace(",", "").replace("٬", "").replace(" ", "")
    multiplier = 1
    if text.endswith('k'):
        multiplier = 1000
    elif text.endswith('m'):
        multiplier = 1_000_000
    try:
        return int(float(re.sub(r"[^\d\.]", "", text)) * multiplier)
    except:
        return 0


# ======================= مدیریت صف =======================
async def add_to_queue(item_id: str):
    now = time.time()
    item_id = item_id.lower()

    async with queue_lock:
        if now - last_processed.get(item_id, 0) < DUPLICATE_WINDOW:
            return
        for _, iid in item_queue:
            if iid == item_id:
                return

        item_queue.append((now, item_id))
        stats["queued"] += 1
        log.info(f"➕ صف: {item_id} | کل: {len(item_queue)}")


async def mark_processed(item_id: str):
    last_processed[item_id] = time.time()
    async with queue_lock:
        temp_list = [x for x in item_queue if x[1] != item_id]
        item_queue.clear()
        item_queue.extend(temp_list)


# ======================= کلیک مستقل و فوری =======================
async def process_click(client, chat_id, message_id, callback_data, btn_text):
    """این تابع در پس‌زمینه سریعاً روی دکمه کلیک می‌کند"""
    global last_action_time
    try:
        await client.request_callback_answer(
            chat_id=chat_id,
            message_id=message_id,
            callback_data=callback_data
        )
        log.info(f"✅ کلیک فوری انجام شد: {btn_text}")
        stats["clicked"] += 1

        # زمان کلیک رو ثبت می‌کنیم تا ورکر بدونه باید وقفه کنه
        async with action_lock:
            last_action_time = time.time()

    except FloodWait as e:
        log.warning(f"⚠️ فلود کلیک: {e.value}s")
        await asyncio.sleep(e.value)
    except Exception as e:
        log.error(f"❌ خطا در کلیک فوری: {e}")


# ══════════════════════════════════════════════════════════
#                    ورکر اصلی (اصلاح شده)
# ══════════════════════════════════════════════════════════
async def sender_worker(app: Client):
    global last_action_time
    log.info("🚀 ورکر توربو فعال شد")

    while True:
        # ─── ① گرفتن آیتم ───
        item_id = None
        async with queue_lock:
            if item_queue:
                _, item_id = item_queue.popleft()

        if not item_id:
            await asyncio.sleep(0.01)
            continue

        # ─── ② بررسی مجدد تکراری ───
        if time.time() - last_processed.get(item_id, 0) < DUPLICATE_WINDOW:
            continue

        # ─── ③ بررسی وقفه اجباری از آخرین کلیک یا ارسال ───
        # اینجا مطمئن میشیم حداقل 1.0 ثانیه از آخرین عملیات گذشته باشه
        while True:
            async with action_lock:
                elapsed = time.time() - last_action_time
                if elapsed >= MIN_DELAY_AFTER_ACTION:
                    break
            await asyncio.sleep(0.1)

        # وقفه تصادفی بین 0 تا 0.5 ثانیه اضافه میکنه تا مجموعا 1.0 تا 1.5 بشه
        await asyncio.sleep(random.uniform(0, MAX_DELAY_AFTER_ACTION - MIN_DELAY_AFTER_ACTION))

        # ─── ④ ارسال پیام ───
        try:
            await app.send_message(BOT_USERNAME, item_id)
            stats["sent"] += 1
            log.info(f"📤 ارسال: {item_id}")

            # زمان ارسال رو ثبت میکنیم
            async with action_lock:
                last_action_time = time.time()

            await mark_processed(item_id)

        except FloodWait as e:
            stats["floods"] += 1
            log.warning(f"🚫 فلود ارسال: {e.value}s")
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            log.error(f"❌ خطا ارسال: {e}")
            await asyncio.sleep(1)
            continue


# ======================= هندلرها =======================
async def handle_bot_reply(client, message):
    # هندلر کاملا مستقل: هر پیامی از ربات که دکمه سفارش داشته باشه رو فورا کلیک میکنه
    if not message.reply_markup or not hasattr(message.reply_markup, "inline_keyboard"):
        return

    for row in message.reply_markup.inline_keyboard:
        for btn in row:
            if btn.text and ("سفارش" in btn.text or "Order" in btn.text):
                # عملیات کلیک رو به پس‌زمینه میسپاریم تا هیچ تاخیری ایجاد نشه
                asyncio.create_task(
                    process_click(client, message.chat.id, message.id, btn.callback_data, btn.text)
                )
                return  # فقط همون دکمه رو کلیک کن و خارج شو


async def handle_channel_message(_, message):
    if not message.text: return
    stats["received"] += 1

    for match in PATTERN_SELL.finditer(message.text):
        item_id = match.group(1).lower()
        name = re.sub(r'[^\w]', '', match.group(2)).lower()
        count = int(match.group(3))
        price = parse_price(match.group(4))

        if price == 0: continue

        profit_val = (count * item_shop.get(name, 0)) - price

        should_buy = False
        if profit and hasattr(profit, 'profit_check'):
            if profit.profit_check(price, profit_val, name, item_shop):
                should_buy = True
        elif profit_val > 0:
            should_buy = True

        if should_buy:
            await add_to_queue(item_id)


# ======================= فچ دیتا =======================
async def fetch_data(app: Client):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://bslife.ir/",
        "Origin": "https://bslife.ir",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest"
    }
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        try:
            async with session.get("https://bslife.ir/") as _:
                pass
        except:
            pass

        while True:
            await asyncio.sleep(((7 + int(random.uniform(4, 9))) / 10))
            try:
                async with session.post(
                        "https://bslife.ir/js/sact.php",
                        data={'data': json.dumps({'o': 't', 'od': 0, 'i': ''})},
                        timeout=10
                ) as resp:
                    if resp.status != 200: continue
                    js = await resp.json(content_type=None)

                    for item in js.get("sells", [])[:8]:
                        code = str(item.get("code", "")).lower()
                        price = parse_price(str(item.get("price", 0)))
                        count = parse_price(str(item.get("val", 0)))
                        item_id = f"s{item.get('id', '')}".lower()

                        if not code or price == 0: continue

                        profit_val = (count * item_shop.get(code, 0)) - price

                        should_buy = False
                        if profit and hasattr(profit, 'profit_check'):
                            if profit.profit_check(price, profit_val, code, item_shop):
                                should_buy = True
                        elif profit_val > 0:
                            should_buy = True

                        if should_buy:
                            await add_to_queue(item_id)

            except Exception:
                await asyncio.sleep(3)


# ======================= ابزارها =======================
async def item_watcher():
    global item_shop
    last_mtime = 0
    while True:
        try:
            if os.path.exists("item.json"):
                mtime = os.path.getmtime("item.json")
                if mtime != last_mtime:
                    with open("item.json", "r", encoding="utf-8") as f:
                        data = json.load(f)
                        item_shop = {k.lower(): v for k, v in data.items()}
                        log.info(f"📦 قیمت‌ها آپدیت شد: {len(item_shop)}")
                        last_mtime = mtime
                    if profit: importlib.reload(profit)
        except:
            pass
        await asyncio.sleep(5)


async def stats_reporter():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        expired = [k for k, v in last_processed.items() if now - v > 60]
        for k in expired: del last_processed[k]
        log.info(f"📊 صف:{len(item_queue)} | ارسال:{stats['sent']} | کلیک:{stats['clicked']}")


# ======================= Main =======================
async def main():
    log.info("🔌 در حال اتصال به تلگرام...")
    app = Client("my_buy_silent", api_id=API_ID, api_hash=API_HASH, phone_number=PHONE_NUMBER)

    await app.start()
    try:
        await app.resolve_peer(CHANNEL)
        await app.resolve_peer(BOT_USERNAME)
    except Exception as e:
        log.error(f"❌ خطا در ریزالو کردن: {e}")

    app.add_handler(MessageHandler(handle_channel_message, filters.chat(CHANNEL)))
    app.add_handler(MessageHandler(handle_bot_reply, filters.chat(BOT_USERNAME) & filters.incoming))
    app.add_handler(EditedMessageHandler(handle_bot_reply, filters.chat(BOT_USERNAME) & filters.incoming))

    log.info("✅ ربات توربو روشن شد.")

    asyncio.create_task(item_watcher())
    asyncio.create_task(fetch_data(app))
    asyncio.create_task(sender_worker(app))
    asyncio.create_task(stats_reporter())

    await asyncio.Event().wait()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass