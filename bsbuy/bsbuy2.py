import asyncio
import os
import re
import json
import time
import random
import importlib
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler, EditedMessageHandler
from dotenv import load_dotenv

# لود uvloop در صورت وجود برای بهینه‌سازی پردازش
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

# ======================= تنظیمات اصلی =======================
API_ID = "29511262"
API_HASH = "c0da1e019c1d69a9abdae20941d923b4"
PHONE_NUMBER = "+989963308164"
BOT_USERNAME = "BslifeBot"
CHANNEL = "BSlifeChat"

DUPLICATE_WINDOW = 10  # جلوگیری از ارسال کد تکراری (ثانیه)
MIN_DELAY_BURST = 0.85  # حداقل فاصله در ارسال‌های رگباری (ثانیه)
MAX_DELAY_BURST = 1.20  # حداکثر فاصله در ارسال‌های رگباری (ثانیه)

# ======================= متغیرهای وضعیت =======================
item_shop: dict = {}
last_processed: dict = {}
last_send_time = 0.0  # زمان دقیق آخرین ارسال به بات

# صف ارسال فوق‌سبک در رم (Asyncio Queue)
send_queue = asyncio.Queue()

PATTERN_SELL = re.compile(
    r"(s\d+):\s*(.+?)\s*x\s*(\d+)\s*->\s*([0-9\.,]+ ?[kKmM]?)",
    re.UNICODE | re.IGNORECASE
)


def parse_price(text: str) -> int:
    text = text.strip().lower().replace(",", "").replace("٬", "").replace(" ", "")
    m = 1
    if text.endswith('k'):
        m = 1000
    elif text.endswith('m'):
        m = 1_000_000
    try:
        return int(float(re.sub(r"[^\d\.]", "", text)) * m)
    except:
        return 0


# ======================= ورکر هوشمند ارسال پیام =======================
async def sender_worker(client: Client):
    """
    این ورکر پیام اول را آنی شلیک می‌کند و پیام‌های بعدی را هوشمندانه کنترل می‌کند
    """
    global last_send_time

    while True:
        # دریافت آیتم از صف (آیتم شامل زمان ایجاد و کد آیتم است)
        created_time, item_id = await send_queue.get()

        # اگر آیتم بیشتر از 12 ثانیه در صف مانده باشد یعنی تاریخ‌گذشته است و رد می‌شود
        if time.time() - created_time > 12:
            send_queue.task_done()
            continue

        now = time.time()
        elapsed = now - last_send_time

        # فاصله تصادفی برای طبیعی بودن و عدم دریافت ارور رگباری
        target_gap = random.uniform(MIN_DELAY_BURST, MAX_DELAY_BURST)

        # محاسبات طلایی: فقط در صورتی صبر کن که از پیام قبلی کمتر از target_gap گذشته باشد
        if elapsed < target_gap:
            wait_needed = target_gap - elapsed
            await asyncio.sleep(wait_needed)

        try:
            # ارسال پیام
            await client.send_message(BOT_USERNAME, item_id, disable_notification=True)
            last_send_time = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] 📤 ارسال موفق به بات: {item_id}")
        except FloodWait as e:
            print(f"⚠️ فلود تلگرام: {e.value} ثانیه")
            last_send_time = time.time() + e.value
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"❌ خطا در ارسال: {e}")
        finally:
            send_queue.task_done()


# ======================= کلیک فوق‌سریع دکمه =======================
async def process_click(client: Client, chat_id: int, message_id: int, callback_data: str):
    """کلیک فوری بدون هیچ‌گونه تاخیر یا تداخل با صف ارسال"""
    try:
        await client.request_callback_answer(
            chat_id=chat_id,
            message_id=message_id,
            callback_data=callback_data
        )
        print(f"[{time.strftime('%H:%M:%S')}] ⚡ دکمه سفارش با موفقیت کلیک شد!")
    except Exception as e:
        print(f"❌ خطا در کلیک: {e}")


# ======================= هندلر نهایی و فوق‌سریع کانال =======================
async def handle_channel_message(client: Client, message):
    text = message.text
    # ۱. فیلتر سریع: اگر پیام خالی بود یا کاراکتر s نداشت سریعاً رد شود
    if not text or "s" not in text.lower():
        return

    now = time.time()

    # ۲. پیمایش تمام آیتم‌های داخل پیام
    for match in PATTERN_SELL.finditer(text):
        item_id = match.group(1).lower()

        # بررسی تکراری نبودن (جلوگیری از محاسبات اضافه)
        if now - last_processed.get(item_id, 0) < DUPLICATE_WINDOW:
            continue

        name = re.sub(r'[^\w]', '', match.group(2)).lower()
        count = int(match.group(3))
        price = parse_price(match.group(4))

        if price == 0:
            continue

        # محاسبه سود بر اساس قیمت واحد
        unit_price = item_shop.get(name, 0)
        profit_val = (count * unit_price) - price

        # بررسی شرایط سوددهی
        should_buy = False
        if profit and hasattr(profit, 'profit_check'):
            if profit.profit_check(price, profit_val, name, unit_price):
                should_buy = True
        elif profit_val > 0:
            should_buy = True

        # اگر سودده بود: ثبت زمان و شلیک به صف ارسال
        if should_buy:
            last_processed[item_id] = now
            send_queue.put_nowait((now, item_id))


# ======================= هندلر دکمه ربات =======================
async def handle_bot_reply(client: Client, message):
    markup = message.reply_markup
    if not markup or not hasattr(markup, "inline_keyboard"):
        return

    for row in markup.inline_keyboard:
        for btn in row:
            if btn.text and ("سفارش" in btn.text or "Order" in btn.text):
                # کلیک بلادرنگ و مستقل در پس‌زمینه
                asyncio.create_task(
                    process_click(client, message.chat.id, message.id, btn.callback_data)
                )
                return


# ======================= مانیتور فایل قیمت‌ها =======================
async def item_watcher():
    global item_shop
    last_mtime = 0
    while True:
        try:
            if os.path.exists("item.json"):
                mtime = os.path.getmtime("item.json")
                if mtime != last_mtime:
                    with open("item.json", "r", encoding="utf-8") as f:
                        item_shop = {k.lower(): v for k, v in json.load(f).items()}
                    last_mtime = mtime
                    print(f"📦 فایل قیمت‌ها بروزرسانی شد: {len(item_shop)} آیتم")
                    if profit:
                        importlib.reload(profit)
        except Exception:
            pass

        # پاکسازی حافظه رم از شناسه‌های قدیمی
        now = time.time()
        for k in list(last_processed.keys()):
            if now - last_processed[k] > 60:
                del last_processed[k]

        await asyncio.sleep(4)


# ======================= استارت برنامه =======================
async def main():
    print("🔌 در حال اتصال به حساب تلگرام...")
    app = Client(
        "my_buy_silent",
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=PHONE_NUMBER,
        workers=4
    )

    await app.start()

    # ریزالو کردن کش اولیه
    try:
        await app.resolve_peer(CHANNEL)
        await app.resolve_peer(BOT_USERNAME)
    except:
        pass

    app.add_handler(MessageHandler(handle_channel_message, filters.chat(CHANNEL)))
    app.add_handler(MessageHandler(handle_bot_reply, filters.chat(BOT_USERNAME) & filters.incoming))
    app.add_handler(EditedMessageHandler(handle_bot_reply, filters.chat(BOT_USERNAME) & filters.incoming))

    print("🚀 ربات با سیستم آنتی‌رگبار هوشمند و سرعت ماکسیمم روشن شد!")

    # اجرای ورکر ارسال و مانیتورینگ
    asyncio.create_task(sender_worker(app))
    asyncio.create_task(item_watcher())

    await asyncio.Event().wait()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass