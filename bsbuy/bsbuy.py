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

try:
    import profit
except ImportError:
    profit = None

load_dotenv()

# ======================= تنظیمات =======================
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")

if not API_ID_RAW or API_ID_RAW == "0":
    raise ValueError("❌ API_ID در فایل .env تنظیم نشده!")
if not API_HASH:
    raise ValueError("❌ API_HASH در فایل .env تنظیم نشده!")
if not PHONE_NUMBER:
    raise ValueError("❌ PHONE_NUMBER در فایل .env تنظیم نشده!")

API_ID = int(API_ID_RAW)
BOT_USERNAME = "BslifeBot"
CHANNEL = "BSlifeChat"

DUPLICATE_WINDOW = 10
DELAY_MIN = 1.0  # حداقل تاخیر بین آیتم‌های پشت سر هم در صف
DELAY_MAX = 1.5  # حداکثر تاخیر بین آیتم‌های پشت سر هم در صف
MAX_QUEUE_SIZE = 10

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
item_queue: asyncio.Queue = None
in_queue: set = set()  # برای جلوگیری از تکراری بودن در صف با هزینه پردازشی صفر
last_processed: dict = {}
last_action_time = 0.0

stats = {
    "received": 0, "queued": 0, "sent": 0,
    "clicked": 0, "floods": 0,
    "avg_ping": 0.0, "last_ping": 0.0,
    "msg_delay": 0.0
}

bot_peer = None

PATTERN_SELL = re.compile(
    r"(s\d+):\s*(.+?)\s*x\s*(\d+)\s*->\s*([0-9\.,]+ ?[kKmM]?)",
    re.UNICODE | re.IGNORECASE
)


def parse_price(text: str) -> int:
    """پارس قیمت - طبق کد اصلی شما"""
    text = text.strip().lower().replace(",", "").replace("٬", "").replace(" ", "")
    multiplier = 1
    if text.endswith('k'):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith('m'):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        return int(float(re.sub(r"[^\d\.]", "", text)) * multiplier)
    except Exception:
        return 0


def gen_random_id():
    return struct.unpack('q', os.urandom(8))[0]


# ══════════════════════ صف (asyncio.Queue) ══════════════════════
def add_to_queue(item_id: str) -> bool:
    now = time.monotonic()
    item_id = item_id.lower()

    if now - last_processed.get(item_id, 0) < DUPLICATE_WINDOW:
        return False

    if item_id in in_queue:
        return False

    if item_queue.full():
        return False

    try:
        item_queue.put_nowait((item_id, now))
        in_queue.add(item_id)
        stats["queued"] += 1
        log.info("➕ صف: %s | سایز: %d", item_id, item_queue.qsize())
        return True
    except asyncio.QueueFull:
        return False


def mark_processed(item_id: str):
    last_processed[item_id] = time.monotonic()


# ══════════════════════ پینگ تلگرام ══════════════════════
async def ping_telegram(client):
    ping_times = []
    while True:
        try:
            start = time.monotonic()
            await client(PingRequest(ping_id=random.randint(0, 2 ** 63)))
            ping_ms = (time.monotonic() - start) * 1000
            ping_times.append(ping_ms)

            if len(ping_times) > 10:
                ping_times.pop(0)

            stats["last_ping"] = round(ping_ms, 1)
            stats["avg_ping"] = round(sum(ping_times) / len(ping_times), 1)

            log.info(
                "🏓 پینگ: %.1fms | میانگین: %.1fms | DC: %s",
                ping_ms, stats["avg_ping"],
                client.session.dc_id if hasattr(client.session, 'dc_id') else '?'
            )
        except Exception as e:
            log.warning("❌ پینگ خطا: %s", e)

        await asyncio.sleep(30)


# ══════════════════════ کلیک فوری ══════════════════════
async def process_click(client, msg_id, callback_data, btn_text, receive_time):
    try:
        req_start = time.monotonic()
        
        # درخواست کلیک فرستاده می‌شود و تا گرفتن جواب صبر می‌کند (بدون تایم‌اوت محدودکننده)
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
            "✅ کلیک: %s | تاخیر کد شما: %.2fms | تایم شبکه و بات: %.0fms | کل تأخیر: %.0fms",
            btn_text, code_delay, click_time, total_delay
        )
        stats["clicked"] += 1
        
    except FloodWaitError as e:
        stats["floods"] += 1
        log.warning("⚠️ فلود کلیک: %ds", e.seconds)
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log.error("❌ خطا کلیک: %s", e)


# ══════════════════════ ورکر سریع ══════════════════════
async def sender_worker(client):
    global last_action_time
    log.info("🚀 ورکر فعال شد")

    while True:
        item_id, queued_time = await item_queue.get()

        # اگر تکراری بود از صف رد میشه و از لیست in_queue هم پاک میشه
        if time.monotonic() - last_processed.get(item_id, 0) < DUPLICATE_WINDOW:
            in_queue.discard(item_id)
            continue

        elapsed = time.monotonic() - last_action_time
        if elapsed < DELAY_MIN:
            wait_time = random.uniform(DELAY_MIN, DELAY_MAX) - elapsed
            if wait_time > 0:
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
            stats["msg_delay"] = round(queue_delay, 1)
            log.info(
                "📤 ارسال: %s | سرعت: %.0fms | تأخیر صف: %.0fms",
                item_id, send_time, queue_delay
            )
            last_action_time = time.monotonic()
            mark_processed(item_id)
            in_queue.discard(item_id)  # <-- حالا اینجا پاک میشه تا تکراری وارد نشه

        except FloodWaitError as e:
            stats["floods"] += 1
            log.warning("🚫 فلود: %ds", e.seconds)
            await asyncio.sleep(e.seconds)
            in_queue.discard(item_id)  # در صورت ارور هم حتما پاک شود
        except Exception as e:
            log.error("❌ خطا ارسال: %s", e)
            await asyncio.sleep(0.3)
            in_queue.discard(item_id)  # در صورت ارور هم حتما پاک شود


# ══════════════════════ هندلرها ══════════════════════
async def handle_bot_reply(event):
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
                    log.info("🔘 دکمه پیدا شد: %s | msg_id: %d", btn.text, msg_id)
                    asyncio.create_task(
                        process_click(event.client, msg_id, btn.data, btn.text, receive_time)
                    )
                    return


async def handle_channel_message(event):
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
            log.info(
                "🎯 آیتم: %s | سود: %d | تشخیص: %.0fms",
                item_id, profit_val, detect_delay
            )
            add_to_queue(item_id)


# ══════════════════════ فچ دیتا (دست‌نخورده) ══════════════════════
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
                        log.info("📦 قیمت‌ها: %d آیتم", len(item_shop))
                        last_mtime = mtime
                    if profit:
                        importlib.reload(profit)
        except Exception:
            pass
        await asyncio.sleep(5)


async def stats_reporter():
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        expired = [k for k, v in last_processed.items() if now - v > 60]
        for k in expired:
            del last_processed[k]
        log.info(
            "📊 صف:%d | دریافت:%d | ارسال:%d | کلیک:%d | فلود:%d | "
            "پینگ:%.0fms | تأخیر‌صف:%.0fms",
            item_queue.qsize(), stats['received'],
            stats['sent'], stats['clicked'], stats['floods'],
            stats['avg_ping'], stats['msg_delay']
        )


# ══════════════════════ Main ══════════════════════
async def main():
    global bot_peer, item_queue

    item_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

    log.info("🔌 اتصال به تلگرام...")

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
    log.info("✅ متصل شد: %s (%s)", me.first_name, me.phone)

    bot_peer = await client.get_input_entity(BOT_USERNAME)
    log.info("✅ bot peer آماده")

    try:
        start = time.monotonic()
        await client(PingRequest(ping_id=random.randint(0, 2 ** 63)))
        ping_ms = (time.monotonic() - start) * 1000
        log.info("🏓 پینگ اولیه: %.1fms", ping_ms)
    except Exception as e:
        log.warning("❌ پینگ اولیه خطا: %s", e)

    @client.on(events.NewMessage(chats=CHANNEL))
    async def _ch(event):
        await handle_channel_message(event)

    @client.on(events.NewMessage(chats=BOT_USERNAME))
    async def _bot_new(event):
        await handle_bot_reply(event)

    @client.on(events.MessageEdited(chats=BOT_USERNAME))
    async def _bot_edit(event):
        await handle_bot_reply(event)

    log.info("✅ ربات روشن شد")

    await asyncio.gather(
        item_watcher(),
        fetch_data(client),
        sender_worker(client),
        stats_reporter(),
        ping_telegram(client),
        client.run_until_disconnected()
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("خاموش شد")