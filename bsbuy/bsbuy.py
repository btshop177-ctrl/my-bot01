import asyncio
import os
import random
import re
import logging
import aiohttp
import json
import time
import struct
import importlib
from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest, SendMessageRequest
from telethon.tl.functions import PingRequest
from telethon.tl.types import KeyboardButtonCallback
from telethon.errors import FloodWaitError

# استفاده از uvloop در صورت موجود بودن روی هاست برای چند برابر کردن سرعت پردازش
try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

try:
    import profit
except ImportError:
    profit = None

load_dotenv()

# ======================= تنظیمات =======================
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")

if not API_ID_RAW or not API_HASH or not PHONE_NUMBER:
    raise ValueError("❌ مقادیر API_ID، API_HASH یا PHONE_NUMBER در .env ناقص است!")

API_ID = int(API_ID_RAW)
BOT_USERNAME = "BslifeBot"
CHANNEL = "BSlifeChat"

DUPLICATE_WINDOW = 10
DELAY_MIN = 0.85  # حداقل تاخیر هوشمند برای جلوگیری از ارور رگباری
DELAY_MAX = 1.15  # حداکثر تاخیر هوشمند
MAX_QUEUE_SIZE = 15

# بهینه‌سازی لاگ بدون سربار دیسک
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("TurboSniper")

# ======================= وضعیت جهانی =======================
item_shop: dict = {}
item_queue: asyncio.Queue = None
in_queue: set = set()
last_processed: dict = {}
last_action_time = 0.0

stats = {
    "received": 0, "queued": 0, "sent": 0,
    "clicked": 0, "floods": 0, "avg_ping": 0.0
}

bot_peer = None

PATTERN_SELL = re.compile(
    r"(s\d+):\s*(.+?)\s*x\s*(\d+)\s*->\s*([0-9\.,]+ ?[kKmM]?)",
    re.UNICODE | re.IGNORECASE
)


def parse_price(text: str) -> int:
    """پارس فوق سریع قیمت بدون پردازش سنگین ریجکس"""
    text = text.strip().lower().replace(",", "").replace("٬", "").replace(" ", "")
    multiplier = 1
    if text.endswith('k'):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith('m'):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        # فیلتر سریع کاراکترهای عددی و ممیز
        clean_num = ''.join(c for c in text if c.isdigit() or c == '.')
        return int(float(clean_num) * multiplier) if clean_num else 0
    except Exception:
        return 0


def gen_random_id():
    """تولید شناسه رندوم پیام تلگرام با بالاترین سرعت"""
    return struct.unpack('q', os.urandom(8))[0]


# ══════════════════════ مدیریت صف ══════════════════════
def add_to_queue(item_id: str) -> bool:
    now = time.monotonic()
    item_id = item_id.lower()

    if (now - last_processed.get(item_id, 0)) < DUPLICATE_WINDOW:
        return False

    if item_id in in_queue or item_queue.full():
        return False

    try:
        item_queue.put_nowait((item_id, now))
        in_queue.add(item_id)
        stats["queued"] += 1
        log.info(f"➕ صف: {item_id} | سایز صف: {item_queue.qsize()}")
        return True
    except asyncio.QueueFull:
        return False


# ══════════════════════ کلیک فوری (زیر ۱ میلی‌ثانیه کد) ══════════════════════
async def process_click(client, msg_id, callback_data, btn_text, receive_time):
    try:
        req_start = time.monotonic()

        # شلیک مستقیم پیامک کلیک بدون واسطه
        await client(GetBotCallbackAnswerRequest(
            peer=bot_peer,
            msg_id=msg_id,
            data=callback_data
        ))

        end_time = time.monotonic()
        click_time = (end_time - req_start) * 1000
        total_delay = (end_time - receive_time) * 1000
        code_delay = (req_start - receive_time) * 1000

        log.info(
            f"⚡ کلیک شد: {btn_text} | تاخیر برنامه: {code_delay:.1f}ms | رفت‌وبرگشت تلگرام: {click_time:.0f}ms | کل: {total_delay:.0f}ms"
        )
        stats["clicked"] += 1

    except FloodWaitError as e:
        stats["floods"] += 1
        log.warning(f"⚠️ فلود کلیک: {e.seconds} ثانیه")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log.error(f"❌ خطا در کلیک: {e}")


# ══════════════════════ ورکر ارسال (هوشمند و ضد رگبار) ══════════════════════
async def sender_worker(client):
    global last_action_time
    log.info("🚀 ورکر شلیک آنی و کنترل رگبار فعال شد")

    while True:
        item_id, queued_time = await item_queue.get()

        # چک مجدد تاریخ انقضا و تکراری بودن
        now = time.monotonic()
        if (now - last_processed.get(item_id, 0)) < DUPLICATE_WINDOW:
            in_queue.discard(item_id)
            item_queue.task_done()
            continue

        # محاسبه هوشمند گپ زمانی
        elapsed = now - last_action_time
        target_delay = random.uniform(DELAY_MIN, DELAY_MAX)

        # اگر از پیام قبلی زمان کافی نگذشته بود صبر کن؛ در غیر اینصورت آنی بفرست
        if elapsed < target_delay:
            wait_time = target_delay - elapsed
            await asyncio.sleep(wait_time)

        try:
            start = time.monotonic()
            await client(SendMessageRequest(
                peer=bot_peer,
                message=item_id,
                random_id=gen_random_id()
            ))
            send_time = (time.monotonic() - start) * 1000
            queue_delay = (time.monotonic() - queued_time) * 1000

            stats["sent"] += 1
            log.info(f"📤 ارسال شد: {item_id} | زمان ارسال تلگرام: {send_time:.0f}ms | معطلی در صف: {queue_delay:.0f}ms")

            last_action_time = time.monotonic()
            last_processed[item_id] = last_action_time

        except FloodWaitError as e:
            stats["floods"] += 1
            log.warning(f"🚫 فلود ارسال: {e.seconds}s")
            last_action_time = time.monotonic() + e.seconds
            await asyncio.sleep(e.seconds)
        except Exception as e:
            log.error(f"❌ خطا در ارسال پیام: {e}")
        finally:
            in_queue.discard(item_id)
            item_queue.task_done()


# ══════════════════════ هندلرها ══════════════════════
async def handle_bot_reply(event):
    """هندلر فوری دریافت پیام از بات برای زدن دکمه سفارش"""
    receive_time = time.monotonic()
    msg = event.message
    markup = msg.reply_markup
    if not markup:
        return

    rows = getattr(markup, 'rows', None)
    if not rows:
        return

    msg_id = msg.id
    for row in rows:
        for btn in row.buttons:
            if isinstance(btn, KeyboardButtonCallback) and btn.data:
                text = (btn.text or '').lower()
                if 'سفارش' in text or 'order' in text:
                    # تفویض کلیک به تسک موازی تا هندلر آزاد شود
                    asyncio.create_task(
                        process_click(event.client, msg_id, btn.data, btn.text, receive_time)
                    )
                    return


async def handle_channel_message(event):
    """هندلر دریافت پیام از کانال"""
    receive_time = time.monotonic()
    text = event.raw_text
    if not text or '->' not in text:
        return

    stats["received"] += 1

    for match in PATTERN_SELL.finditer(text):
        item_id = match.group(1).lower()
        name = re.sub(r'[^\w]', '', match.group(2)).lower()
        count = int(match.group(3))
        price = parse_price(match.group(4))

        if price == 0:
            continue

        unit_price = item_shop.get(name, 0)
        profit_val = (count * unit_price) - price

        should_buy = False
        if profit and hasattr(profit, 'profit_check'):
            if profit.profit_check(price, profit_val, name, unit_price):
                should_buy = True
        elif profit_val > 0:
            should_buy = True

        if should_buy:
            detect_delay = (time.monotonic() - receive_time) * 1000
            log.info(f"🎯 شکار: {item_id} | سود: {profit_val} | شناسایی در: {detect_delay:.1f}ms")
            add_to_queue(item_id)


# ══════════════════════ فچ دیتا (کاملاً دست‌نخورده و ایمن) ══════════════════════
async def fetch_data(client):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
                    if resp.status != 200:
                        continue
                    js = await resp.json(content_type=None)

                    for item in js.get("sells", [])[:8]:
                        code = str(item.get("code", "")).lower()
                        price = parse_price(str(item.get("price", 0)))
                        count = parse_price(str(item.get("val", 0)))
                        item_id = f"s{item.get('id', '')}".lower()

                        if not code or price == 0:
                            continue

                        unit_price = item_shop.get(code, 0)
                        profit_val = (count * unit_price) - price

                        should_buy = False
                        if profit and hasattr(profit, 'profit_check'):
                            if profit.profit_check(price, profit_val, code, unit_price):
                                should_buy = True
                        elif profit_val > 0:
                            should_buy = True

                        if should_buy:
                            add_to_queue(item_id)
            except Exception:
                await asyncio.sleep(3)


# ══════════════════════ ابزارها ══════════════════════
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
                        log.info(f"📦 بروزرسانی قیمت‌ها: {len(item_shop)} آیتم")
                        last_mtime = mtime
                    if profit:
                        importlib.reload(profit)
        except Exception:
            pass
        await asyncio.sleep(4)


async def stats_reporter():
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        expired = [k for k, v in list(last_processed.items()) if now - v > 60]
        for k in expired:
            del last_processed[k]
        log.info(
            f"📊 آمار -> صف: {item_queue.qsize()} | دریافت: {stats['received']} | ارسال: {stats['sent']} | کلیک: {stats['clicked']} | فلود: {stats['floods']}"
        )


# ══════════════════════ Main ══════════════════════
async def main():
    global bot_peer, item_queue

    item_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

    log.info("🔌 در حال اتصال به تلگرام...")

    client = TelegramClient(
        "sniper_session",
        API_ID,
        API_HASH,
        auto_reconnect=True,
        retry_delay=1,
        request_retries=3,
        flood_sleep_threshold=0
    )

    await client.start(phone=PHONE_NUMBER)
    me = await client.get_me()
    log.info(f"✅ متصل شد: {me.first_name}")

    bot_peer = await client.get_input_entity(BOT_USERNAME)
    log.info("✅ Peer ربات با موفقیت Cache شد.")

    # هندلرهای پیام‌ها
    client.add_event_handler(handle_channel_message, events.NewMessage(chats=CHANNEL))
    client.add_event_handler(handle_bot_reply, events.NewMessage(chats=BOT_USERNAME))
    client.add_event_handler(handle_bot_reply, events.MessageEdited(chats=BOT_USERNAME))

    log.info("🚀 ربات با بالاترین سرعت و ایمنی فعال شد.")

    await asyncio.gather(
        item_watcher(),
        fetch_data(client),
        sender_worker(client),
        stats_reporter(),
        client.run_until_disconnected()
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("خاموش شد.")