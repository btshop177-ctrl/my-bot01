import asyncio
import re
import logging
import httpx
from telethon import TelegramClient, events

from config import (
    USERBOT_API_ID, USERBOT_API_HASH, USERBOT_PHONE,
    USERBOT_SESSION, BSLIFE_BOT, BSLIFE_OUR_NAME, COIN_NAME,
    BOT_TOKEN, USERBOT_PROXY_TYPE, USERBOT_PROXY_HOST, USERBOT_PROXY_PORT,
)
from database import Database

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("userbot")

db = Database()


# ═══════════════════════════════════
#            PROXY
# ═══════════════════════════════════
def get_proxy():
    if not USERBOT_PROXY_TYPE or not USERBOT_PROXY_HOST or not USERBOT_PROXY_PORT:
        logger.info("🌐 No proxy")
        return None
    pt = USERBOT_PROXY_TYPE.lower().strip()
    try:
        import python_socks
        types = {
            "socks5": python_socks.ProxyType.SOCKS5,
            "socks4": python_socks.ProxyType.SOCKS4,
            "http": python_socks.ProxyType.HTTP,
        }
        p = types.get(pt)
        if p:
            logger.info(f"🔌 Proxy: {pt}://{USERBOT_PROXY_HOST}:{USERBOT_PROXY_PORT}")
            return (p, USERBOT_PROXY_HOST, USERBOT_PROXY_PORT)
    except ImportError:
        pass
    try:
        import socks
        types = {
            "socks5": socks.SOCKS5,
            "socks4": socks.SOCKS4,
            "http": socks.HTTP,
        }
        p = types.get(pt)
        if p:
            logger.info(f"🔌 Proxy (PySocks): {pt}://{USERBOT_PROXY_HOST}:{USERBOT_PROXY_PORT}")
            return (p, USERBOT_PROXY_HOST, USERBOT_PROXY_PORT)
    except ImportError:
        pass
    logger.error("❌ No proxy library! pip install python-socks[asyncio]")
    return None


proxy = get_proxy()
client = TelegramClient(USERBOT_SESSION, USERBOT_API_ID, USERBOT_API_HASH, proxy=proxy)


# ═══════════════════════════════════
#         NOTIFY (Bot API)
# ═══════════════════════════════════
async def notify_user(user_id: int, text: str):
    """ارسال پیام به کاربر از طریق Bot API"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient() as http:
            await http.post(
                url,
                json={"chat_id": user_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
    except Exception as e:
        logger.warning(f"notify error {user_id}: {e}")


# ═══════════════════════════════════
#         HELPERS
# ═══════════════════════════════════
def parse_bslife_amount(text: str):
    """
    پارس مبلغ از متن BsLifeBot
    پشتیبانی از:
      1000, 1,000, 1،000, 1٬000
      ۱۰۰۰, ۱,۰۰۰
    """
    try:
        match = re.search(r'انتقال\s*:\s*([0-9۰-۹,٬،]+)\s*سکه', text)
        if not match:
            return None
        raw = match.group(1).strip()
        # تبدیل اعداد فارسی به انگلیسی
        raw = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        # حذف جداکننده‌ها
        raw = raw.replace(",", "").replace("،", "").replace("٬", "")
        if not raw.isdigit():
            return None
        return int(raw)
    except Exception:
        return None


def parse_sender(text: str):
    """استخراج فرستنده از متن"""
    match = re.search(r'از\s*:\s*(\S+)', text)
    return match.group(1).strip() if match else None


def parse_receiver(text: str):
    """استخراج گیرنده از متن"""
    match = re.search(r'به\s*:\s*(\S+)', text)
    return match.group(1).strip() if match else None


def check_error(text: str) -> bool:
    """چک خطاهای شناخته‌شده BsLifeBot"""
    if "نیاز به تایید" in text:
        return False
    if "رسید گیفت" in text:
        return False
    if "گیفت انجام شد" in text:
        return False
    error_keywords = [
        "آخرین بازدید",
        "خطا",
        "موجودی کافی نیست",
        "یافت نشد",
        "نامعتبر",
        "محدودیت",
        "بلاک",
    ]
    for keyword in error_keywords:
        if keyword in text:
            return True
    return False


# ═══════════════════════════════════
#     RESPONSE QUEUE (برداشت)
# ═══════════════════════════════════
_response_queue = asyncio.Queue()
_watching = False  # فقط وقتی برداشت داریم True میشه
_withdraw_lock = asyncio.Lock()  # قفل برای جلوگیری از تداخل


async def flush_queue():
    """خالی کردن صف قبل از شروع برداشت جدید"""
    while not _response_queue.empty():
        try:
            _response_queue.get_nowait()
        except asyncio.QueueEmpty:
            break


async def wait_for_response(timeout: int = 15):
    """منتظر پیام جدید یا edit شده از BsLifeBot"""
    try:
        return await asyncio.wait_for(_response_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


# ═══════════════════════════════════
#    BSLIFE MESSAGE HANDLERS
# ═══════════════════════════════════
@client.on(events.NewMessage(from_users=BSLIFE_BOT))
async def on_new_message(event):
    """پیام جدید از BsLifeBot"""
    text = event.raw_text or ""
    logger.info(f"📩 BsLife NEW: {text[:120]}")

    # اگه در حال برداشت هستیم → صف
    if _watching:
        await _response_queue.put(event.message)

    # واریز خودکار (فقط رسیدهایی که مقصدشون ما هستیم)
    if "رسید" in text and ("به:" in text or "به :" in text):
        await handle_deposit(text)


@client.on(events.MessageEdited(from_users=BSLIFE_BOT))
async def on_edited_message(event):
    """پیام ادیت‌شده از BsLifeBot (بعد از کلیک تایید)"""
    text = event.raw_text or ""
    logger.info(f"📝 BsLife EDIT: {text[:120]}")

    if _watching:
        await _response_queue.put(event.message)


# ═══════════════════════════════════
#         DEPOSIT (واریز خودکار)
# ═══════════════════════════════════
async def handle_deposit(text: str):
    """
    وقتی کسی به ما گیفت میزنه:
    🎁 رسید گیفت:
    🔄انتقال: 1,000 سکه
    ↗️از: caliber
    ↙️به: negative
    """
    # پاکسازی کاراکترهای مخفی
    clean = text.replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")

    logger.info(f"📥 Checking deposit: {clean[:150]}")

    # گیرنده
    receiver = parse_receiver(clean)
    if not receiver:
        logger.warning("Deposit: 'به' not found")
        return

    # فقط اگه گیرنده ما باشیم
    if receiver.lower() != BSLIFE_OUR_NAME.lower():
        logger.info(f"Deposit: receiver '{receiver}' != '{BSLIFE_OUR_NAME}', skip")
        return

    # فرستنده
    sender = parse_sender(clean)
    if not sender:
        logger.warning("Deposit: 'از' not found")
        return

    # مبلغ (با پشتیبانی از 1,000 و اعداد فارسی)
    amount = parse_bslife_amount(clean)
    if amount is None or amount <= 0:
        logger.warning("Deposit: amount not found or invalid")
        return

    logger.info(f"📥 Deposit: {sender} → {amount}")

    # پیدا کردن کاربر
    user = db.find_user_by_special_name(sender)
    if not user:
        logger.info(f"User '{sender}' not found, skip.")
        return

    # شارژ حساب
    new_bal = db.add_coins(user["user_id"], amount, f"واریز BsLife")
    db.log_deposit(user["user_id"], sender, amount)
    db.log_activity(user["user_id"], "deposit", f"{amount}")

    logger.info(f"✅ {sender} +{amount} → {new_bal}")

    # اطلاع به کاربر
    await notify_user(
        user["user_id"],
        f"✅ **واریز موفق!**\n\n"
        f"💰 مبلغ: **{amount}** {COIN_NAME}\n"
        f"💎 موجودی: **{new_bal}** {COIN_NAME}",
    )


# ═══════════════════════════════════
#      WITHDRAW (برداشت)
# ═══════════════════════════════════
async def process_withdraw(req):
    """پردازش یک درخواست برداشت - با قفل"""
    global _watching

    rid = req["id"]
    uid = req["user_id"]
    name = req["special_name"]
    amount = req["amount"]

    logger.info(f"🔄 Withdraw #{rid}: {name} → {amount}")

    # قفل: فقط یک برداشت همزمان
    async with _withdraw_lock:
        try:
            db.update_withdraw_status(rid, "processing")

            # فعال کردن گوش دادن به پاسخ‌ها
            _watching = True
            await flush_queue()

            # ارسال gift
            bslife = await client.get_entity(BSLIFE_BOT)
            await client.send_message(bslife, f"gift {name} {amount}")

            # ── پاسخ اول ──
            resp = await wait_for_response(timeout=15)

            if resp is None:
                logger.warning(f"#{rid}: timeout")
                db.update_withdraw_status(rid, "failed", "timeout")
                await notify_user(uid,
                    f"❌ **برداشت #{rid} ناموفق!**\n\n"
                    f"ربات بی‌اسلایف پاسخ نداد.\n"
                    f"لطفاً با ادمین تماس بگیرید.\n"
                    f"⚠️ بازگشت سکه انجام **نمی‌شود**.")
                return

            resp_text = resp.raw_text or ""
            logger.info(f"#{rid} resp: {resp_text[:100]}")

            # ── خطا قبل از تایید ──
            if check_error(resp_text):
                logger.warning(f"#{rid}: error before confirm")
                db.update_withdraw_status(rid, "failed", "error_first")
                await notify_user(uid,
                    f"❌ **برداشت #{rid} ناموفق!**\n\n"
                    f"{resp_text}\n\n"
                    f"⚠️ بازگشت سکه انجام **نمی‌شود**.")
                return

            # ── رسید مستقیم ──
            if "رسید گیفت" in resp_text:
                db.update_withdraw_status(rid, "success", "direct")
                logger.info(f"✅ #{rid}: direct success!")
                await notify_user(uid,
                    f"✅ **برداشت #{rid} موفق!**\n\n"
                    f"💰 مبلغ: **{amount}** {COIN_NAME}\n"
                    f"👤 به: **{name}**\n\n"
                    f"📝 **رسید:**\n{resp_text}")
                return

            # ── نیاز به تایید ──
            if "نیاز به تایید" in resp_text or "تایید" in resp_text:
                logger.info(f"#{rid}: needs confirmation")

                if not resp.buttons or len(resp.buttons) == 0:
                    db.update_withdraw_status(rid, "failed", "no_buttons")
                    await notify_user(uid,
                        f"❌ **برداشت #{rid} ناموفق!**\n\n"
                        f"دکمه تایید پیدا نشد.\n"
                        f"⚠️ بازگشت سکه انجام **نمی‌شود**.")
                    return

                # کلیک دکمه تایید
                try:
                    await resp.click(0)
                    logger.info(f"#{rid}: clicked confirm")
                except Exception as e:
                    logger.error(f"#{rid}: click failed: {e}")
                    db.update_withdraw_status(rid, "failed", "click_failed")
                    await notify_user(uid,
                        f"❌ **برداشت #{rid} ناموفق!**\n\n"
                        f"خطا در تایید.\n"
                        f"⚠️ بازگشت سکه انجام **نمی‌شود**.")
                    return

                # ── بعد از تایید: تا 3 پاسخ رو چک کن ──
                receipt = None
                for attempt in range(3):
                    msg = await wait_for_response(timeout=10)

                    if msg is None:
                        logger.info(f"#{rid}: attempt {attempt + 1} - no response")
                        break

                    msg_text = msg.raw_text or ""
                    logger.info(f"#{rid}: attempt {attempt + 1} - got: {msg_text[:80]}")

                    # خطا بعد از تایید
                    if check_error(msg_text):
                        logger.warning(f"#{rid}: error after confirm")
                        db.update_withdraw_status(rid, "failed", "error_after_confirm")
                        await notify_user(uid,
                            f"❌ **برداشت #{rid} ناموفق!**\n\n"
                            f"{msg_text}\n\n"
                            f"⚠️ بازگشت سکه انجام **نمی‌شود**.")
                        return

                    # رسید
                    if "رسید گیفت" in msg_text:
                        receipt = msg
                        break

                    # پیام واسط (مثل "گیفت انجام شد") → ادامه بده
                    logger.info(f"#{rid}: intermediate, waiting...")

                # نتیجه نهایی
                if receipt:
                    receipt_text = receipt.raw_text or ""
                    db.update_withdraw_status(rid, "success", "completed")
                    logger.info(f"✅ #{rid}: success!")

                    # بررسی: رسید مال برداشت خودمونه؟
                    receipt_receiver = parse_receiver(receipt_text)
                    if receipt_receiver and receipt_receiver.lower() == name.lower():
                        await notify_user(uid,
                            f"✅ **برداشت #{rid} موفق!**\n\n"
                            f"💰 مبلغ: **{amount}** {COIN_NAME}\n"
                            f"👤 به: **{name}**\n\n"
                            f"📝 **رسید:**\n{receipt_text}")
                    else:
                        # رسید مال کس دیگه‌ای بود (نباید اتفاق بیفته با lock)
                        logger.error(f"#{rid}: receipt mismatch! expected={name}, got={receipt_receiver}")
                        await notify_user(uid,
                            f"⚠️ **برداشت #{rid}**\n\n"
                            f"عملیات انجام شد ولی رسید تطابق ندارد.\n"
                            f"لطفاً با ادمین تماس بگیرید.")
                else:
                    db.update_withdraw_status(rid, "unknown", "no_receipt")
                    await notify_user(uid,
                        f"⚠️ **برداشت #{rid}**\n\n"
                        f"تایید شد ولی رسید دریافت نشد.\n"
                        f"لطفاً با ادمین تماس بگیرید.")
                return

            # ── پاسخ غیرمنتظره ──
            logger.warning(f"#{rid}: unexpected: {resp_text[:100]}")
            db.update_withdraw_status(rid, "failed", "unexpected")
            await notify_user(uid,
                f"❌ **برداشت #{rid} ناموفق!**\n\n"
                f"{resp_text}\n\n"
                f"⚠️ بازگشت سکه انجام **نمی‌شود**.")

        except Exception as e:
            logger.error(f"#{rid} error: {e}")
            db.update_withdraw_status(rid, "failed", str(e)[:100])
            await notify_user(uid,
                f"❌ **خطای سیستمی!**\n\n"
                f"لطفاً با ادمین تماس بگیرید.\n"
                f"⚠️ بازگشت سکه انجام **نمی‌شود**.")
        finally:
            _watching = False


# ═══════════════════════════════════
#     WITHDRAW LOOP (صف برداشت)
# ═══════════════════════════════════
async def withdraw_loop():
    """هر 3 ثانیه DB چک میکنه، بین هر درخواست 2.5 ثانیه تاخیر"""
    logger.info("🔄 Withdraw loop started")
    while True:
        try:
            pending = db.get_pending_withdraws()
            if pending:
                logger.info(f"📋 {len(pending)} pending")
                for i, req in enumerate(pending):
                    await process_withdraw(req)
                    # تاخیر 2.5 ثانیه فقط بین درخواست‌ها
                    if i < len(pending) - 1:
                        logger.info(f"⏱ Waiting 2.5s before next withdraw...")
                        await asyncio.sleep(2.5)
        except Exception as e:
            logger.error(f"Loop error: {e}")
        await asyncio.sleep(3)


# ═══════════════════════════════════
#              MAIN
# ═══════════════════════════════════
async def main():
    logger.info("🔌 Connecting...")
    await client.start(phone=USERBOT_PHONE)

    me = await client.get_me()
    logger.info(f"✅ Userbot: {me.first_name} (ID: {me.id})")

    try:
        bslife = await client.get_entity(BSLIFE_BOT)
        logger.info(f"✅ BsLifeBot: {bslife.id}")
    except Exception as e:
        logger.error(f"❌ BsLifeBot not found: {e}")

    asyncio.create_task(withdraw_loop())
    logger.info("👁️ Watching...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())