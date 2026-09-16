"""
ربات مدیریت سلف (چندکاربره)
─────────────────────────────
• مدیر اصلی (ADMIN_ID) می‌تواند برای کاربران سلف فعال/غیرفعال کند و زمان اعتبار تعیین کند
• کاربران از طریق ربات آموزش ساخت اپ تلگرام را می‌بینند و api_id / api_hash را ثبت می‌کنند
• پس از احراز هویت (شماره → کد → رمز دومرحله‌ای) یک سشن با نام یکتا و یک config.json
  اختصاصی برای کاربر ساخته می‌شود
• اولین کانفیگ و جیسون متعلق به مدیر است (db.ensure_admin)
• هر کاربر فعال، یک پروسه‌ی مجزای main.py با env مخصوص خودش دارد

اجرا:
    API_ID=... API_HASH=... BOT_TOKEN=... ADMIN_ID=... python manager_bot.py
"""

import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
from dotenv import load_dotenv

# ─── لود .env از پوشه‌ی خود فایل (مستقل از محل اجرا) ───
from db import SELF_DIR as _DOTENV_DIR
load_dotenv(os.path.join(_DOTENV_DIR, ".env"))
load_dotenv()  # fallback: .env محل اجرا (بدون override)


def _env(*names, default=None):
    for name in names:
        val = os.getenv(name)
        if val not in (None, ""):
            return val
    return default


# ─── تنظیمات (با پیام خطای واضح) ───
if not _env("MANAGER_API_ID", "API_ID"):
    raise SystemExit("❌ API_ID را در فایل .env (پوشه self) تنظیم کنید")
if not _env("MANAGER_API_HASH", "API_HASH"):
    raise SystemExit("❌ API_HASH را در فایل .env (پوشه self) تنظیم کنید")

API_ID = int(_env("MANAGER_API_ID", "API_ID"))
API_HASH = _env("MANAGER_API_HASH", "API_HASH")
BOT_TOKEN = _env("MANAGER_BOT_TOKEN", "BOT_TOKEN")
ADMIN_ID = int(_env("ADMIN_ID", "OWNER_ID", default="0") or "0")

if not ADMIN_ID:
    raise SystemExit("❌ متغیر ADMIN_ID را در .env تنظیم کنید (آیدی عددی مدیر)")
if not BOT_TOKEN:
    raise SystemExit(
        "❌ متغیر BOT_TOKEN (یا MANAGER_BOT_TOKEN) را در .env تنظیم کنید"
    )

if not _env("MANAGER_BOT_TOKEN"):
    print("⚠️" * 20)
    print("⚠️ MANAGER_BOT_TOKEN تنظیم نشده → از همان BOT_TOKEN استفاده می‌شود.")
    print("⚠️ اگر main.py (سلف قدیمی) با همین توکن هم‌زمان در حال اجرا باشد،")
    print("⚠️ آپدیت‌های /start بین دو پروسه تقسیم می‌شوند و ربات مدیریت")
    print("⚠️ به پیام‌ها پاسخ نمی‌دهد!")
    print("💡 راه‌حل: یا main.py را متوقف کنید، یا یک ربات جداگانه با")
    print("💡 @BotFather بسازید و توکنش را در MANAGER_BOT_TOKEN بگذارید.")
    print("⚠️" * 20)

from telethon import TelegramClient, events, Button
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    PasswordHashInvalidError,
    ApiIdInvalidError,
    FloodWaitError,
)

from db import (
    UsersDatabase, SELF_DIR, SESSIONS_DIR,
    STATUS_FA, STATUS_ACTIVE, STATUS_PENDING, STATUS_NEW,
    STATUS_REGISTERED, STATUS_STOPPED, STATUS_EXPIRED,
)

# ─── پروکسی (اختیاری) ───
PROXY_SCHEME = os.getenv("PROXY_SCHEME", "").lower()
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "") or None
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "") or None


def build_proxy():
    if not PROXY_SCHEME or not PROXY_HOST or not PROXY_PORT:
        return None
    try:
        import python_socks
    except ImportError:
        return None
    scheme_map = {
        "socks5": python_socks.ProxyType.SOCKS5,
        "socks4": python_socks.ProxyType.SOCKS4,
        "http": python_socks.ProxyType.HTTP,
    }
    proxy_type = scheme_map.get(PROXY_SCHEME)
    if not proxy_type:
        return None
    proxy = {
        "proxy_type": proxy_type,
        "addr": PROXY_HOST,
        "port": int(PROXY_PORT),
        "rdns": True,
    }
    if PROXY_USERNAME:
        proxy["username"] = PROXY_USERNAME
    if PROXY_PASSWORD:
        proxy["password"] = PROXY_PASSWORD
    return proxy


# ─── دیتابیس + ربات ───
db = UsersDatabase(ADMIN_ID)
proxy_config = build_proxy()

bot = TelegramClient(
    os.path.join(SESSIONS_DIR, "manager_bot"),
    API_ID, API_HASH,
    proxy=proxy_config,
)

LOGS_DIR = os.path.join(SELF_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

import functools
import traceback


def safe_handler(func):
    """هر خطای هندلر را در کنسول چاپ و به کاربر هم اطلاع می‌دهد"""
    @functools.wraps(func)
    async def wrapper(event):
        try:
            await func(event)
        except Exception as e:
            print(f"❌ خطا در هندلر {func.__name__}:")
            traceback.print_exc()
            try:
                await event.respond(
                    f"❌ **خطای ربات رخ داد**\n`{str(e)[:250]}`"
                )
            except Exception:
                pass
    return wrapper


# ─── حالت‌های موقت ───
USER_STATES = {}       # tg_id → {"state": ..., ...}
LOGIN_CLIENTS = {}     # tg_id → {"client":..., "phone":..., "hash":..., "tmp":...}
RUNNING = {}           # tg_id → Popen
RESTART_LOG = {}       # tg_id → [timestamps]
ADMIN_STATE = {}       # admin state (custom days و ...)

DURATIONS = [
    (1, "۱ روز"),
    (7, "۷ روز"),
    (30, "۳۰ روز"),
    (90, "۹۰ روز"),
    (None, "نامحدود ♾"),
]

API_TUTORIAL = (
    "📱 **آموزش ساخت اپ تلگرام و دریافت API**\n\n"
    "**قدم ۱:** به سایت زیر بروید:\n"
    "👉 my.telegram.org\n\n"
    "**قدم ۲:** شماره تلگرام خود را با کد کشور وارد کنید\n"
    "(مثال: `+98912xxxxxxx`) و کد تاییدی که تلگرام\n"
    "برایتان می‌فرستد را وارد کنید.\n\n"
    "**قدم ۳:** روی **API development tools** کلیک کنید.\n\n"
    "**قدم ۴:** روی **Create application** کلیک کنید و\n"
    "دو فیلد `App title` و `Short name` را پر کنید\n"
    "(بقیه فیلدها اختیاری است، پلتفرم = Other)\n\n"
    "**قدم ۵:** بعد از ساخت، دو مقدار به شما می‌دهد:\n"
    "▸ `api_id` → یک عدد (مثلاً `12345678`)\n"
    "▸ `api_hash` → یک رشته ۳۲ کاراکتری\n\n"
    "⚠️ این دو مقدار محرمانه هستند؛ به کسی ندهید.\n\n"
    "وقتی ساختید، دکمه **ثبت API** را بزنید و\n"
    "مقادیر را وارد کنید 👇"
)


# ═══════════════════════════════════════
# مدیریت پروسه‌های سلف کاربران
# ═══════════════════════════════════════

def start_self_process(user):
    """اجرای main.py برای یک کاربر با env اختصاصی"""
    tg_id = user["telegram_id"]
    session_rel = user.get("session", "")
    if not session_rel:
        print(f"⚠️ کاربر {tg_id} سشن ندارد")
        return None

    old = RUNNING.get(tg_id)
    if old and old.poll() is None:
        return old  # در حال اجراست

    env = os.environ.copy()
    env["SELF_API_ID"] = str(user["api_id"]) if user.get("api_id") else ""
    env["SELF_API_HASH"] = user.get("api_hash") or ""
    env["SELF_SESSION"] = session_rel
    env["SELF_CONFIG"] = user.get("config") or ""
    env["SELF_PHONE"] = user.get("phone") or ""
    env["SELF_BOT_SESSION"] = f"sessions/bot_u{tg_id}"
    if user.get("bot_token"):
        env["SELF_BOT_TOKEN"] = user["bot_token"]
    else:
        env.pop("SELF_BOT_TOKEN", None)

    log_path = os.path.join(LOGS_DIR, f"self_{tg_id}.log")
    log_file = open(log_path, "a", encoding="utf-8")

    try:
        proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=SELF_DIR,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        RUNNING[tg_id] = proc
        print(f"🚀 سلف کاربر {tg_id} اجرا شد (PID {proc.pid})")
        return proc
    except Exception as e:
        print(f"❌ خطا در اجرای سلف {tg_id}: {e}")
        return None


def stop_self_process(tg_id):
    """توقف پروسه‌ی سلف یک کاربر"""
    proc = RUNNING.pop(tg_id, None)
    if not proc:
        return False
    if proc.poll() is not None:
        return False
    try:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        print(f"🛑 سلف کاربر {tg_id} متوقف شد")
        return True
    except Exception as e:
        print(f"⚠️ خطا در توقف سلف {tg_id}: {e}")
        return False


def is_running(tg_id):
    proc = RUNNING.get(tg_id)
    return bool(proc and proc.poll() is None)


# ═══════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════

def is_admin(tg_id):
    return tg_id == ADMIN_ID


def user_display(user):
    name = user.get("name") or ""
    username = user.get("username") or ""
    acc_id = user.get("account_id")
    tg_id = user.get("telegram_id")
    parts = []
    if name:
        parts.append(f"**{name}**")
    if username:
        parts.append(f"@{username}")
    parts.append(f"`{acc_id or tg_id}`")
    return " ".join(parts)


def remaining_text(user):
    days = db.remaining_days(user)
    if days is None:
        return "نامحدود ♾"
    if days <= 0:
        return "منقضی شده"
    return f"{days} روز"


def fmt_ts(ts):
    if not ts:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def user_detail_text(user):
    status = STATUS_FA.get(user["status"], user["status"])
    running = "🟢 در حال اجرا" if is_running(user["telegram_id"]) else "⚫ متوقف"
    api = "✅" if user.get("api_id") else "❌"
    session = "✅" if user.get("session") else "❌"
    bottoken = "✅" if user.get("bot_token") else "❌"

    text = (
        f"👤 **جزئیات کاربر**\n\n"
        f"  ▸ نام: {user.get('name') or '-'}\n"
        f"  ▸ یوزرنیم: {'@' + user['username'] if user.get('username') else '-'}\n"
        f"  ▸ آیدی ربات: `{user['telegram_id']}`\n"
        f"  ▸ آیدی اکانت: `{user.get('account_id') or '-'}`\n"
        f"  ▸ وضعیت: {status}\n"
        f"  ▸ پروسه: {running}\n"
        f"  ▸ اعتبار: {remaining_text(user)}\n"
        f"  ▸ فعال‌سازی: {fmt_ts(user.get('activated_at'))}\n"
        f"  ▸ انقضا: {fmt_ts(user.get('expires_at'))}\n\n"
        f"  ▸ API: {api} | سشن: {session} | توکن ربات: {bottoken}\n"
        f"  ▸ سشن: `{user.get('session') or '-'}`\n"
        f"  ▸ کانفیگ: `{user.get('config') or '-'}`"
    )
    return text


def main_menu_buttons(tg_id):
    rows = [
        [Button.inline("📱 ساخت اپ و دریافت API", data="menu_api")],
        [Button.inline("🔐 فعال‌سازی سلف (ساخت سشن)", data="menu_activate")],
        [Button.inline("🤖 توکن ربات پنل (اختیاری)", data="menu_bottoken")],
        [Button.inline("📊 وضعیت من", data="menu_status")],
    ]
    if is_admin(tg_id):
        rows.insert(0, [Button.inline("👑 پنل مدیریت", data="admin_panel")])
    return rows


def cancel_button(back="menu_main"):
    return [[Button.inline("❌ انصراف", data=back)]]


def duration_buttons(tg_id, prefix="admin_act"):
    rows = []
    row = []
    for days, label in DURATIONS:
        val = str(days) if days else "inf"
        row.append(Button.inline(label, data=f"{prefix}_{tg_id}_{val}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Button.inline("✏️ مدت دلخواه (روز)", data=f"admin_custom_{tg_id}")])
    rows.append([Button.inline("🔙 بازگشت", data=f"admin_user_{tg_id}")])
    return rows


def clear_state(tg_id):
    USER_STATES.pop(tg_id, None)
    ADMIN_STATE.pop(tg_id, None)


async def cleanup_login(tg_id, remove_file=True):
    """پاکسازی کلاینت لاگین موقت"""
    info = LOGIN_CLIENTS.pop(tg_id, None)
    if not info:
        return
    try:
        client = info.get("client")
        if client:
            await client.disconnect()
    except Exception:
        pass
    if remove_file and info.get("tmp"):
        for suffix in (".session", ".session-journal"):
            path = info["tmp"] + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


# ═══════════════════════════════════════
# اعلان‌ها
# ═══════════════════════════════════════

async def notify_user_activated(user, days):
    tg_id = user["telegram_id"]
    dur = f"{days} روز" if days else "نامحدود ♾"
    try:
        await bot.send_message(
            tg_id,
            "✅ **سلف شما فعال شد!**\n\n"
            f"  ▸ مدت اعتبار: **{dur}**\n"
            f"  ▸ انقضا: {fmt_ts(user.get('expires_at'))}\n\n"
            "حالا در چت **Saved Messages** خودتان دستور `راهنما`\n"
            "را بفرستید تا لیست امکانات را ببینید."
        )
    except Exception as e:
        print(f"⚠️ اعلان فعال‌سازی به {tg_id}: {e}")


async def notify_user_stopped(user, reason=""):
    tg_id = user["telegram_id"]
    try:
        await bot.send_message(
            tg_id,
            f"🔴 **سلف شما غیرفعال شد**\n{reason}"
        )
    except Exception:
        pass


async def notify_admin_pending(user):
    """اعلان درخواست جدید به مدیر با دکمه تایید/رد"""
    tg_id = user["telegram_id"]
    try:
        await bot.send_message(
            ADMIN_ID,
            "🔔 **درخواست فعال‌سازی سلف جدید**\n\n"
            f"  ▸ کاربر: {user_display(user)}\n"
            f"  ▸ شماره: `{user.get('phone') or '-'}`\n"
            f"  ▸ سشن: `{user.get('session')}`\n"
            f"  ▸ کانفیگ: `{user.get('config')}`\n\n"
            "مدت اعتبار را انتخاب کنید یا رد کنید:",
            buttons=duration_buttons(tg_id) + [
                [Button.inline("🚫 رد درخواست", data=f"admin_reject_{tg_id}")]
            ],
        )
    except Exception as e:
        print(f"⚠️ اعلان به ادمین: {e}")


# ═══════════════════════════════════════
# فعال‌سازی واقعی کاربر
# ═══════════════════════════════════════

async def do_activate(tg_id, days, actor="admin"):
    user = db.get_user(tg_id)
    if not user:
        return "❌ کاربر یافت نشد"
    if not user.get("session"):
        return "❌ کاربر هنوز سشن نساخته است"

    user = db.activate(tg_id, days=days)
    proc = start_self_process(user)

    if proc is None:
        return "❌ خطا در اجرای پروسه سلف"

    await notify_user_activated(user, days)
    dur = f"{days} روز" if days else "نامحدود"
    print(f"✅ سلف {tg_id} توسط {actor} فعال شد ({dur})")
    return f"✅ سلف کاربر برای **{dur}** فعال شد"


async def do_stop(tg_id, notify=True):
    user = db.get_user(tg_id)
    if not user:
        return "❌ کاربر یافت نشد"
    stop_self_process(tg_id)
    db.stop(tg_id)
    if notify:
        await notify_user_stopped(user)
    print(f"🔴 سلف {tg_id} غیرفعال شد")
    return "🔴 سلف کاربر غیرفعال شد"


# ═══════════════════════════════════════
# هندلر پیام‌های متنی (ورودی مرحله‌ای)
# ═══════════════════════════════════════

@bot.on(events.NewMessage(pattern="^/(start|admin)$"))
@safe_handler
async def cmd_start(event):
    if not event.is_private:
        return
    tg_id = event.sender_id
    print(f"📩 {event.raw_text} از کاربر {tg_id}")
    clear_state(tg_id)
    await cleanup_login(tg_id)

    if event.raw_text == "/admin" and not is_admin(tg_id):
        await event.respond("⛔ این بخش فقط برای مدیر اصلی است.")
        return

    user = db.get_user(tg_id)
    if not user:
        sender = await event.get_sender()
        db.upsert_user(
            tg_id,
            name=getattr(sender, "first_name", "") or "",
            username=getattr(sender, "username", "") or "",
        )

    welcome = (
        "👋 **به ربات مدیریت سلف خوش آمدید**\n\n"
        "با این ربات می‌توانید سلف تلگرامی خود را راه‌اندازی\n"
        "و مدیریت کنید:\n\n"
        "۱️⃣ ابتدا **اپ تلگرام** بسازید و `api_id` و `api_hash`\n"
        "    را دریافت کنید\n"
        "2️⃣ سپس با شماره خود وارد شوید تا **سشن** ساخته شود\n"
        "3️⃣ مدیر برایتان **فعال‌سازی** می‌کند ✅\n\n"
        "یک گزینه را انتخاب کنید 👇"
    )
    if is_admin(tg_id):
        welcome = (
            "👑 **مدیر اصلی، خوش آمدید**\n\n"
            "▸ از «پنل مدیریت» کاربران را فعال/غیرفعال کنید\n"
            "▸ خودتان هم می‌توانید مانند یک کاربر سلف بسازید\n\n"
            + welcome.split("\n\n", 1)[1]
        )

    if event.raw_text == "/admin":
        users = db.all_users()
        active = len([u for u in users if u["status"] == STATUS_ACTIVE])
        pending = len(db.pending_users())
        running = len([t for t in RUNNING if is_running(t)])
        await event.respond(
            "👑 **پنل مدیریت سلف**\n\n"
            f"  ▸ کل کاربران: `{len(users)}`\n"
            f"  ▸ فعال: `{active}` | در انتظار: `{pending}`\n"
            f"  ▸ پروسه‌های در حال اجرا: `{running}`\n",
            buttons=[
                [Button.inline(f"⏳ درخواست‌های در انتظار ({pending})", data="admin_pending")],
                [Button.inline("👥 لیست کاربران", data="admin_users_0")],
                [Button.inline("🏠 منوی اصلی", data="menu_main")],
            ]
        )
        return

    await event.respond(welcome, buttons=main_menu_buttons(tg_id))


@bot.on(events.NewMessage())
@safe_handler
async def text_input_handler(event):
    if not event.is_private:
        return
    if event.raw_text and event.raw_text.startswith("/"):
        return
    tg_id = event.sender_id
    state = USER_STATES.get(tg_id) or ADMIN_STATE.get(tg_id)
    if not state:
        return

    text = event.raw_text.strip() if event.raw_text else ""
    step = state.get("state")

    # ─── ثبت api_id ───
    if step == "api_id":
        if not text.isdigit():
            await event.respond(
                "❌ `api_id` باید فقط **عدد** باشد. دوباره ارسال کنید:",
                buttons=cancel_button()
            )
            return
        state["api_id"] = int(text)
        state["state"] = "api_hash"
        await event.respond(
            "✅ `api_id` ثبت شد.\n\n"
            "حالا `api_hash` را ارسال کنید\n"
            "(رشته ۳۲ کاراکتری):",
            buttons=cancel_button()
        )
        return

    # ─── ثبت api_hash ───
    if step == "api_hash":
        if not re.fullmatch(r"[0-9a-fA-F]{32}", text):
            await event.respond(
                "❌ `api_hash` معمولاً ۳۲ کاراکتر (0-9 و a-f) است.\n"
                "دوباره ارسال کنید:",
                buttons=cancel_button()
            )
            return
        db.set_api(tg_id, state["api_id"], text.lower())
        clear_state(tg_id)
        await event.respond(
            "✅ **اطلاعات API شما ثبت شد**\n\n"
            f"  ▸ api_id: `{state['api_id']}`\n"
            f"  ▸ api_hash: `{text.lower()}`\n\n"
            "حالا می‌توانید سلف را فعال کنید 👇",
            buttons=[
                [Button.inline("🔐 فعال‌سازی سلف", data="menu_activate")],
                [Button.inline("🏠 منوی اصلی", data="menu_main")],
            ]
        )
        return

    # ─── شماره موبایل ───
    if step == "phone":
        phone = text.replace(" ", "").replace("-", "")
        if re.fullmatch(r"09\d{9}", phone):
            phone = "+98" + phone[1:]
        if not re.fullmatch(r"\+\d{8,15}", phone):
            await event.respond(
                "❌ فرمت شماره اشتباه است.\n"
                "مثال صحیح: `+98912xxxxxxx`",
                buttons=cancel_button()
            )
            return

        user = db.get_user(tg_id)
        api_id = (user or {}).get("api_id") or API_ID
        api_hash = (user or {}).get("api_hash") or API_HASH

        await cleanup_login(tg_id)
        tmp_session = os.path.join(
            SESSIONS_DIR, f"tmp_{tg_id}_{int(time.time())}"
        )

        client = TelegramClient(
            tmp_session, api_id, api_hash, proxy=proxy_config
        )
        try:
            await client.connect()
            sent = await client.send_code_request(phone)
        except ApiIdInvalidError:
            await event.respond(
                "❌ **api_id یا api_hash نامعتبر است**\n"
                "از بخش API دوباره ثبت کنید.",
                buttons=[[Button.inline("📱 ثبت API", data="menu_api")]]
            )
            await client.disconnect()
            return
        except PhoneNumberInvalidError:
            await event.respond(
                "❌ شماره نامعتبر است. دوباره ارسال کنید:",
                buttons=cancel_button()
            )
            await cleanup_login(tg_id)
            return
        except FloodWaitError as e:
            await event.respond(
                f"⏳ محدودیت تلگرام: {e.seconds} ثانیه دیگر تلاش کنید."
            )
            await cleanup_login(tg_id)
            return
        except Exception as e:
            await event.respond(
                f"❌ خطا در ارسال کد: `{str(e)[:120]}`",
                buttons=cancel_button()
            )
            await cleanup_login(tg_id)
            return

        LOGIN_CLIENTS[tg_id] = {
            "client": client,
            "phone": phone,
            "hash": sent.phone_code_hash,
            "tmp": tmp_session,
            "api_id": api_id,
            "api_hash": api_hash,
            "tries": 0,
        }
        state["state"] = "code"
        await event.respond(
            "📨 **کد تایید ارسال شد**\n\n"
            "کدی که تلگرام برایتان فرستاد را همین‌جا ارسال کنید.\n"
            f"▸ شماره: `{phone}`\n\n"
            "💡 کد را می‌توانید با فاصله هم بفرستید: `1 2 3 4 5`",
            buttons=cancel_button()
        )
        return

    # ─── کد تایید ───
    if step == "code":
        info = LOGIN_CLIENTS.get(tg_id)
        if not info:
            clear_state(tg_id)
            await event.respond(
                "❌ نشست منقضی شده، دوباره شروع کنید:",
                buttons=[[Button.inline("🔐 فعال‌سازی سلف", data="menu_activate")]]
            )
            return

        code = re.sub(r"[^\d]", "", text)
        if not code:
            await event.respond(
                "❌ کد فقط شامل عدد است. دوباره ارسال کنید:",
                buttons=cancel_button()
            )
            return

        client = info["client"]
        try:
            await client.sign_in(
                phone=info["phone"],
                code=code,
                phone_code_hash=info["hash"],
            )
        except SessionPasswordNeededError:
            state["state"] = "password"
            await event.respond(
                "🔑 **حساب شما رمز دومرحله‌ای دارد**\n"
                "رمز (2FA) خود را ارسال کنید:",
                buttons=cancel_button()
            )
            return
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            info["tries"] += 1
            if info["tries"] >= 3:
                await event.respond("❌ کد اشتباه زیاد تکرار شد. دوباره شروع کنید.")
                await cleanup_login(tg_id)
                clear_state(tg_id)
                return
            await event.respond(
                "❌ کد اشتباه یا منقضی است. دوباره ارسال کنید:",
                buttons=cancel_button()
            )
            return
        except Exception as e:
            await event.respond(f"❌ خطا: `{str(e)[:120]}`")
            await cleanup_login(tg_id)
            clear_state(tg_id)
            return

        await finish_login(event, tg_id, state)
        return

    # ─── رمز دومرحله‌ای ───
    if step == "password":
        info = LOGIN_CLIENTS.get(tg_id)
        if not info:
            clear_state(tg_id)
            await event.respond("❌ نشست منقضی شده، دوباره شروع کنید.")
            return

        try:
            await event.delete()  # رمز را نگه نمی‌داریم
        except Exception:
            pass

        client = info["client"]
        try:
            await client.sign_in(password=text)
        except PasswordHashInvalidError:
            await event.respond(
                "❌ رمز اشتباه است. دوباره ارسال کنید:",
                buttons=cancel_button()
            )
            return
        except Exception as e:
            await event.respond(f"❌ خطا: `{str(e)[:120]}`")
            await cleanup_login(tg_id)
            clear_state(tg_id)
            return

        await finish_login(event, tg_id, state)
        return

    # ─── توکن ربات پنل ───
    if step == "bot_token":
        if not re.fullmatch(r"\d{6,12}:[\w-]{30,40}", text):
            await event.respond(
                "❌ فرمت توکن اشتباه است.\n"
                "توکن را از @BotFather بگیرید. مثال:\n"
                "`123456789:AAH...xyz`",
                buttons=cancel_button()
            )
            return
        user = db.upsert_user(tg_id, bot_token=text)
        clear_state(tg_id)

        # اگر سلف در حال اجراست، با توکن جدید ری‌استارت شود
        restarted = False
        if user and user["status"] == STATUS_ACTIVE and is_running(tg_id):
            stop_self_process(tg_id)
            restarted = bool(start_self_process(user))

        extra = ""
        if restarted:
            extra = "\n\n♻️ سلف شما برای اعمال توکن جدید ری‌استارت شد."
        await event.respond(
            "✅ **توکن ربات پنل ذخیره شد**\n\n"
            "از دفعه بعد که سلف شما اجرا شود، پنل اینلاین\n"
            "با همین ربات کار می‌کند." + extra,
            buttons=[[Button.inline("🏠 منوی اصلی", data="menu_main")]]
        )
        return

    # ─── مدت دلخواه (ادمین) ───
    if step == "custom_days":
        if not is_admin(tg_id):
            return
        if not text.isdigit() or int(text) < 1:
            await event.respond(
                "❌ یک عدد صحیح بزرگ‌تر از صفر (روز) ارسال کنید:",
                buttons=[[Button.inline("🔙 بازگشت", data=f"admin_user_{state.get('target')}")]]
            )
            return
        target = state.get("target")
        extend_mode = state.get("extend", False)
        clear_state(tg_id)
        if extend_mode:
            user = db.extend(target, int(text))
            if user and user["status"] == STATUS_ACTIVE:
                start_self_process(user)
            await event.respond(
                f"✅ اعتبار کاربر `{target}` به میزان **{text} روز** تمدید شد.\n"
                f"  ▸ انقضای جدید: {fmt_ts(user.get('expires_at'))}",
                buttons=[[Button.inline("🔙 بازگشت", data=f"admin_user_{target}")]]
            )
            try:
                await bot.send_message(
                    target,
                    f"⏰ اعتبار سلف شما **{text} روز** تمدید شد.\n"
                    f"  ▸ انقضای جدید: {fmt_ts(user.get('expires_at'))}"
                )
            except Exception:
                pass
        else:
            result = await do_activate(target, int(text))
            await event.respond(
                result,
                buttons=[[Button.inline("🔙 بازگشت", data=f"admin_user_{target}")]]
            )
        return


@bot.on(events.NewMessage())
@safe_handler
async def fallback_handler(event):
    """پاسخ به دستورات ناشناخته/لغو - تضمین می‌کند ربات همیشه جواب بدهد"""
    if not event.is_private:
        return
    text = (event.raw_text or "").strip()
    if not text:
        return
    tg_id = event.sender_id

    # دستور ناشناخته با / → نمایش منو (start/admin با هندلر خودشان)
    if text.startswith("/"):
        if re.match(r"^/(start|admin)\b", text):
            return
        clear_state(tg_id)
        await cleanup_login(tg_id)
        await event.respond(
            "🏠 **منوی اصلی** — یک گزینه را انتخاب کنید 👇",
            buttons=main_menu_buttons(tg_id)
        )
        return

    # کلمات رایج → نمایش منو
    if text.lower() in ("منو", "menu", "panel", "پنل", "شروع", "لغو", "انصراف", "بازگشت"):
        clear_state(tg_id)
        await cleanup_login(tg_id)
        await event.respond(
            "🏠 **منوی اصلی** — یک گزینه را انتخاب کنید 👇",
            buttons=main_menu_buttons(tg_id)
        )
        return


# ═══════════════════════════════════════
# پایان لاگین: ساخت سشن یکتا + config.json
# ═══════════════════════════════════════

async def finish_login(event, tg_id, state):
    info = LOGIN_CLIENTS.get(tg_id)
    if not info:
        return

    client = info["client"]
    try:
        me = await client.get_me()
    except Exception as e:
        await event.respond(f"❌ خطا در دریافت اطلاعات حساب: `{str(e)[:100]}`")
        await cleanup_login(tg_id)
        clear_state(tg_id)
        return

    account_id = me.id
    name = " ".join(filter(None, [me.first_name or "", me.last_name or ""])).strip()
    username = me.username or ""
    phone = info["phone"]

    # قطع اتصال تا فایل سشن نهایی شود
    await client.disconnect()

    # سشن قبلی کاربر را پیدا کن تا بعداً پاک شود
    old_user = db.get_user(tg_id) or {}
    old_session = old_user.get("session", "")

    # ساخت رکورد: نام یکتا + config.json اختصاصی
    user = db.set_session(
        tg_id, phone=phone, account_id=account_id,
        name=name, username=username
    )
    final_session_rel = user["session"]
    final_abs = os.path.join(SELF_DIR, final_session_rel + ".session")

    # انتقال سشن موقت به نام نهایی یکتا
    moved = False
    for suffix in (".session", ".session-journal"):
        src = info["tmp"] + suffix
        dst = os.path.join(SELF_DIR, final_session_rel + suffix)
        if os.path.exists(src):
            try:
                shutil.move(src, dst)
                moved = True
            except Exception as e:
                print(f"⚠️ خطا در انتقال سشن: {e}")

    LOGIN_CLIENTS.pop(tg_id, None)
    clear_state(tg_id)

    if not moved or not os.path.exists(final_abs):
        await event.respond(
            "❌ خطا در ذخیره سشن. دوباره تلاش کنید.",
            buttons=[[Button.inline("🔐 تلاش مجدد", data="menu_activate")]]
        )
        return

    # پاک کردن سشن قدیمی اگر متفاوت بود
    if old_session and old_session != final_session_rel:
        for suffix in (".session", ".session-journal"):
            old_path = os.path.join(SELF_DIR, old_session + suffix)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass

    # اگر سلف قبلاً در حال اجراست، متوقفش کن (سشن جدید جایگزین شد)
    if is_running(tg_id):
        stop_self_process(tg_id)

    print(
        f"🔐 سشن جدید: {final_session_rel} | کاربر: {name} ({account_id})"
    )

    # اگر مدیر لاگین کرد → فعال‌سازی خودکار نامحدود
    if is_admin(tg_id):
        result = await do_activate(tg_id, None, actor="خود مدیر")
        await event.respond(
            "✅ **ورود موفق - مدیر اصلی**\n\n"
            f"  ▸ حساب: **{name}** (`{account_id}`)\n"
            f"  ▸ سشن: `{final_session_rel}`\n"
            f"  ▸ کانفیگ: `{user['config']}`\n\n"
            f"{result}",
            buttons=[[Button.inline("👑 پنل مدیریت", data="admin_panel")]]
        )
        return

    await event.respond(
        "✅ **ورود موفقیت‌آمیز بود!**\n\n"
        f"  ▸ حساب: **{name}** (`{account_id}`)\n"
        f"  ▸ سشن: `{final_session_rel}`\n"
        f"  ▸ کانفیگ: `{user['config']}`\n\n"
        "⏳ درخواست شما برای مدیر ارسال شد.\n"
        "بعد از تایید و تعیین مدت، سلف شما فعال می‌شود.",
        buttons=[[Button.inline("📊 وضعیت من", data="menu_status")]]
    )
    await notify_admin_pending(user)


# ═══════════════════════════════════════
# هندلر دکمه‌ها
# ═══════════════════════════════════════

@bot.on(events.CallbackQuery())
@safe_handler
async def callback_handler(event):
    tg_id = event.sender_id
    data = event.data.decode("utf-8")

    # ─── منوی اصلی ───
    if data == "menu_main":
        clear_state(tg_id)
        await cleanup_login(tg_id)
        await event.edit(
            "🏠 **منوی اصلی**\nیک گزینه را انتخاب کنید 👇",
            buttons=main_menu_buttons(tg_id)
        )
        return

    # ─── آموزش ساخت اپ ───
    if data == "menu_api":
        await event.edit(
            API_TUTORIAL,
            buttons=[
                [Button.inline("📝 ثبت API ID و API Hash", data="api_start")],
                [Button.inline("🔙 منوی اصلی", data="menu_main")],
            ],
            link_preview=False
        )
        return

    if data == "api_start":
        USER_STATES[tg_id] = {"state": "api_id"}
        await event.edit(
            "📝 **ثبت اطلاعات API**\n\n"
            "عدد `api_id` را ارسال کنید\n"
            "(مثال: `12345678`):",
            buttons=cancel_button()
        )
        return

    # ─── فعال‌سازی سلف ───
    if data == "menu_activate":
        user = db.get_user(tg_id)
        if not user or not user.get("api_id"):
            await event.answer(
                "⚠️ ابتدا باید API را ثبت کنید", alert=True
            )
            await event.edit(
                API_TUTORIAL,
                buttons=[
                    [Button.inline("📝 ثبت API ID و API Hash", data="api_start")],
                    [Button.inline("🔙 منوی اصلی", data="menu_main")],
                ],
                link_preview=False
            )
            return

        if user.get("status") == STATUS_ACTIVE and is_running(tg_id):
            await event.answer(
                "✅ سلف شما از قبل فعال و در حال اجراست", alert=True
            )
            return

        if user.get("status") == STATUS_PENDING:
            await event.answer(
                "⏳ درخواست شما از قبل ثبت شده و در انتظار تایید مدیر است",
                alert=True
            )
            return

        USER_STATES[tg_id] = {"state": "phone"}
        await event.edit(
            "🔐 **فعال‌سازی سلف - ساخت سشن**\n\n"
            "شماره تلگرام خود را با کد کشور ارسال کنید:\n"
            "مثال: `+98912xxxxxxx`\n\n"
            "⚠️ شماره باید مال اکانتی باشد که می‌خواهید\n"
            "سلف روی آن اجرا شود.",
            buttons=cancel_button()
        )
        return

    # ─── توکن ربات پنل ───
    if data == "menu_bottoken":
        USER_STATES[tg_id] = {"state": "bot_token"}
        await event.edit(
            "🤖 **ثبت توکن ربات پنل (اختیاری)**\n\n"
            "اگر می‌خواهید پنل اینلاین (دستور `پنل`) کار کند:\n"
            "۱. به @BotFather بروید\n"
            "۲. با `/newbot` یک ربات بسازید\n"
            "۳. با `/setinline` حالت اینلاین را روشن کنید\n"
            "۴. توکن ربات را همین‌جا ارسال کنید\n\n"
            "اگر نمی‌خواهید، انصراف بزنید - بقیه امکانات\n"
            "بدون ربات هم کار می‌کنند.",
            buttons=cancel_button()
        )
        return

    # ─── وضعیت من ───
    if data == "menu_status":
        user = db.get_user(tg_id)
        if not user or user.get("status") == STATUS_NEW:
            await event.edit(
                "📭 شما هنوز ثبت‌نام نکرده‌اید.\n"
                "ابتدا API را ثبت کنید:",
                buttons=[
                    [Button.inline("📱 ثبت API", data="menu_api")],
                    [Button.inline("🔙 منوی اصلی", data="menu_main")],
                ]
            )
            return

        status = STATUS_FA.get(user["status"], user["status"])
        text = (
            "📊 **وضعیت شما**\n\n"
            f"  ▸ وضعیت: {status}\n"
            f"  ▸ API: {'✅ ثبت شده' if user.get('api_id') else '❌'}\n"
            f"  ▸ سشن: {'✅ ' + user.get('session', '') if user.get('session') else '❌ ساخته نشده'}\n"
            f"  ▸ توکن ربات پنل: {'✅' if user.get('bot_token') else '❌'}\n"
        )
        if user["status"] == STATUS_ACTIVE:
            text += (
                f"  ▸ اعتبار باقی‌مانده: **{remaining_text(user)}**\n"
                f"  ▸ انقضا: {fmt_ts(user.get('expires_at'))}\n"
            )
        if user["status"] == STATUS_PENDING:
            text += "\n⏳ منتظر تایید مدیر باشید."
        if user["status"] in (STATUS_STOPPED, STATUS_EXPIRED):
            text += "\nبرای فعال‌سازی مجدد با مدیر در تماس باشید."

        await event.edit(
            text, buttons=[[Button.inline("🔙 منوی اصلی", data="menu_main")]]
        )
        return

    # ═══════════════════════════════════════
    # دکمه‌های مدیریت
    # ═══════════════════════════════════════

    if data.startswith("admin_"):
        if not is_admin(tg_id):
            await event.answer("⛔ فقط مدیر اصلی", alert=True)
            return

        # ─── پنل مدیریت ───
        if data == "admin_panel":
            users = db.all_users()
            active = len([u for u in users if u["status"] == STATUS_ACTIVE])
            pending = len(db.pending_users())
            running = len([t for t in RUNNING if is_running(t)])
            await event.edit(
                "👑 **پنل مدیریت سلف**\n\n"
                f"  ▸ کل کاربران: `{len(users)}`\n"
                f"  ▸ فعال: `{active}` | در انتظار: `{pending}`\n"
                f"  ▸ پروسه‌های در حال اجرا: `{running}`\n",
                buttons=[
                    [Button.inline(f"⏳ درخواست‌های در انتظار ({pending})", data="admin_pending")],
                    [Button.inline("👥 لیست کاربران", data="admin_users_0")],
                    [Button.inline("🏠 منوی اصلی", data="menu_main")],
                ]
            )
            return

        # ─── درخواست‌های در انتظار ───
        if data == "admin_pending":
            pend = db.pending_users()
            if not pend:
                await event.edit(
                    "📭 **درخواست در انتظاری وجود ندارد**",
                    buttons=[[Button.inline("🔙 پنل مدیریت", data="admin_panel")]]
                )
                return
            rows = []
            for u in pend:
                label = user_display(u).replace("**", "")
                rows.append([
                    Button.inline(f"👤 {label[:30]}", data=f"admin_user_{u['telegram_id']}"),
                    Button.inline("✅", data=f"admin_dur_{u['telegram_id']}"),
                    Button.inline("🚫", data=f"admin_reject_{u['telegram_id']}"),
                ])
            rows.append([Button.inline("🔙 پنل مدیریت", data="admin_panel")])
            await event.edit(
                f"⏳ **درخواست‌های در انتظار:** `{len(pend)}`\n\n"
                "✅ فعال‌سازی | 🚫 رد درخواست",
                buttons=rows
            )
            return

        # ─── لیست کاربران (صفحه‌بندی) ───
        m = re.fullmatch(r"admin_users_(\d+)", data)
        if m:
            page = int(m.group(1))
            users = sorted(
                db.all_users(),
                key=lambda u: u.get("created_at", 0)
            )
            per_page = 8
            total_pages = max(1, (len(users) + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            chunk = users[page * per_page:(page + 1) * per_page]

            rows = []
            for u in chunk:
                st = STATUS_FA.get(u["status"], "").split()[0]
                name = (u.get("name") or u.get("username")
                        or str(u["telegram_id"]))
                extra = ""
                if u["status"] == STATUS_ACTIVE:
                    rem = db.remaining_days(u)
                    extra = f" ({rem}ر)" if rem is not None else " (∞)"
                rows.append([Button.inline(
                    f"{st} {name[:24]}{extra}",
                    data=f"admin_user_{u['telegram_id']}"
                )])

            nav = []
            if page > 0:
                nav.append(Button.inline("◀️ قبلی", data=f"admin_users_{page - 1}"))
            if page < total_pages - 1:
                nav.append(Button.inline("بعدی ▶️", data=f"admin_users_{page + 1}"))
            if nav:
                rows.append(nav)
            rows.append([Button.inline("🔙 پنل مدیریت", data="admin_panel")])

            await event.edit(
                f"👥 **کاربران** (صفحه {page + 1}/{total_pages})",
                buttons=rows
            )
            return

        # ─── جزئیات کاربر ───
        m = re.fullmatch(r"admin_user_(\d+)", data)
        if m:
            uid = int(m.group(1))
            user = db.get_user(uid)
            if not user:
                await event.answer("❌ کاربر یافت نشد", alert=True)
                return

            rows = []
            if user["status"] == STATUS_PENDING:
                rows.append([Button.inline("✅ فعال‌سازی + تعیین مدت", data=f"admin_dur_{uid}")])
                rows.append([Button.inline("🚫 رد درخواست", data=f"admin_reject_{uid}")])
            elif user["status"] == STATUS_ACTIVE:
                rows.append([Button.inline("⏰ تمدید اعتبار", data=f"admin_ext_{uid}")])
                rows.append([Button.inline("🔴 غیرفعال کردن", data=f"admin_stop_{uid}")])
            elif user["status"] in (STATUS_STOPPED, STATUS_EXPIRED):
                if user.get("session"):
                    rows.append([Button.inline("♻️ فعال‌سازی مجدد", data=f"admin_dur_{uid}")])
            rows.append([Button.inline("🗑 حذف کاربر", data=f"admin_del_{uid}")])
            rows.append([Button.inline("🔙 لیست کاربران", data="admin_users_0")])

            await event.edit(user_detail_text(user), buttons=rows)
            return

        # ─── انتخاب مدت ───
        m = re.fullmatch(r"admin_dur_(\d+)", data)
        if m:
            uid = int(m.group(1))
            user = db.get_user(uid)
            if not user:
                await event.answer("❌ کاربر یافت نشد", alert=True)
                return
            await event.edit(
                f"⏰ **مدت اعتبار سلف برای {user_display(user)}**\n\n"
                "یکی از گزینه‌ها را انتخاب کنید:",
                buttons=duration_buttons(uid)
            )
            return

        # ─── تمدید (همان دکمه‌های مدت با پرچم تمدید) ───
        m = re.fullmatch(r"admin_ext_(\d+)", data)
        if m:
            uid = int(m.group(1))
            user = db.get_user(uid)
            if not user:
                await event.answer("❌ کاربر یافت نشد", alert=True)
                return
            await event.edit(
                f"⏰ **تمدید اعتبار {user_display(user)}**\n"
                f"انقضای فعلی: {fmt_ts(user.get('expires_at'))}\n\n"
                "مدت تمدید را انتخاب کنید:",
                buttons=duration_buttons(uid, prefix="admin_extd")
            )
            return

        # ─── فعال‌سازی با مدت انتخابی ───
        m = re.fullmatch(r"admin_act_(\d+)_(inf|\d+)", data)
        if m:
            uid = int(m.group(1))
            days = None if m.group(2) == "inf" else int(m.group(2))
            result = await do_activate(uid, days)
            await event.edit(
                result,
                buttons=[[Button.inline("🔙 جزئیات کاربر", data=f"admin_user_{uid}")]]
            )
            return

        # ─── تمدید با مدت انتخابی ───
        m = re.fullmatch(r"admin_extd_(\d+)_(inf|\d+)", data)
        if m:
            uid = int(m.group(1))
            if m.group(2) == "inf":
                user = db.upsert_user(uid, expires_at=None, duration_days=None)
                txt = "✅ اعتبار کاربر **نامحدود** شد"
            else:
                days = int(m.group(2))
                user = db.extend(uid, days)
                txt = f"✅ اعتبار کاربر **{days} روز** تمدید شد"
            if user and user["status"] == STATUS_ACTIVE:
                start_self_process(user)
            try:
                await bot.send_message(
                    uid,
                    f"{txt}\n  ▸ انقضا: {fmt_ts(user.get('expires_at'))}"
                )
            except Exception:
                pass
            await event.edit(
                f"{txt}\n  ▸ انقضا: {fmt_ts(user.get('expires_at'))}",
                buttons=[[Button.inline("🔙 جزئیات کاربر", data=f"admin_user_{uid}")]]
            )
            return

        # ─── مدت دلخواه ───
        m = re.fullmatch(r"admin_custom_(\d+)", data)
        if m:
            uid = int(m.group(1))
            ADMIN_STATE[tg_id] = {"state": "custom_days", "target": uid}
            await event.edit(
                "✏️ **مدت دلخواه**\n\n"
                "تعداد روز اعتبار را (فقط عدد) ارسال کنید:\n"
                "مثال: `45`",
                buttons=[[Button.inline("🔙 بازگشت", data=f"admin_user_{uid}")]]
            )
            return

        # ─── غیرفعال کردن ───
        m = re.fullmatch(r"admin_stop_(\d+)", data)
        if m:
            uid = int(m.group(1))
            result = await do_stop(uid)
            await event.edit(
                result,
                buttons=[[Button.inline("🔙 جزئیات کاربر", data=f"admin_user_{uid}")]]
            )
            return

        # ─── رد درخواست ───
        m = re.fullmatch(r"admin_reject_(\d+)", data)
        if m:
            uid = int(m.group(1))
            stop_self_process(uid)
            user = db.delete_user(uid)
            try:
                await bot.send_message(
                    uid,
                    "🚫 **درخواست فعال‌سازی سلف شما رد شد**\n"
                    "برای اطلاعات بیشتر با مدیر در تماس باشید."
                )
            except Exception:
                pass
            await event.edit(
                f"🚫 درخواست **{(user or {}).get('name', uid)}** رد و حذف شد",
                buttons=[[Button.inline("🔙 پنل مدیریت", data="admin_panel")]]
            )
            return

        # ─── حذف کاربر ───
        m = re.fullmatch(r"admin_del_(\d+)", data)
        if m:
            uid = int(m.group(1))
            await event.edit(
                "⚠️ **حذف کامل کاربر؟**\n\n"
                "سشن، کانفیگ و همه اطلاعات کاربر حذف و\n"
                "سلف او متوقف می‌شود. این عمل برگشت‌ناپذیر است.",
                buttons=[
                    [Button.inline("✅ بله، حذف کن", data=f"admin_delok_{uid}")],
                    [Button.inline("🔙 انصراف", data=f"admin_user_{uid}")],
                ]
            )
            return

        m = re.fullmatch(r"admin_delok_(\d+)", data)
        if m:
            uid = int(m.group(1))
            stop_self_process(uid)
            user = db.delete_user(uid)
            name = (user or {}).get("name", str(uid))
            try:
                await bot.send_message(uid, "🗑 حساب سلف شما توسط مدیر حذف شد.")
            except Exception:
                pass
            await event.edit(
                f"🗑 کاربر **{name}** به‌طور کامل حذف شد",
                buttons=[[Button.inline("🔙 لیست کاربران", data="admin_users_0")]]
            )
            return


# ═══════════════════════════════════════
# Watchdog: انقضا + ری‌استارت پروسه‌ها
# ═══════════════════════════════════════

async def watchdog_loop():
    print("👁 Watchdog فعال شد (بررسی هر ۶۰ ثانیه)")
    while True:
        try:
            await asyncio.sleep(60)
            now = time.time()

            for user in db.all_users():
                uid = user["telegram_id"]

                # انقضای اعتبار
                if user["status"] == STATUS_ACTIVE and db.is_expired(user):
                    stop_self_process(uid)
                    db.expire(uid)
                    print(f"⏰ اعتبار {uid} تمام شد → سلف متوقف شد")
                    try:
                        await bot.send_message(
                            uid,
                            "⏰ **اعتبار سلف شما به پایان رسید**\n"
                            "برای تمدید با مدیر در تماس باشید."
                        )
                    except Exception:
                        pass
                    try:
                        await bot.send_message(
                            ADMIN_ID,
                            f"⏰ اعتبار سلف {user_display(user)} به پایان رسید و متوقف شد.",
                            buttons=[[Button.inline("♻️ تمدید/فعال‌سازی", data=f"admin_user_{uid}")]]
                        )
                    except Exception:
                        pass
                    continue

                # ری‌استارت خودکار پروسه‌های کرش‌کرده (حداکثر ۵ بار در ساعت)
                if user["status"] == STATUS_ACTIVE and not db.is_expired(user):
                    proc = RUNNING.get(uid)
                    if proc is not None and proc.poll() is not None:
                        attempts = [
                            t for t in RESTART_LOG.get(uid, [])
                            if now - t < 3600
                        ]
                        if len(attempts) < 5:
                            print(f"♻️ سلف {uid} کرش کرد → ری‌استارت")
                            RESTART_LOG[uid] = attempts + [now]
                            start_self_process(user)
                        else:
                            if len(attempts) == 5:
                                RESTART_LOG[uid] = attempts + [now]
                                try:
                                    await bot.send_message(
                                        ADMIN_ID,
                                        f"⚠️ سلف {user_display(user)} بیش از ۵ بار در یک ساعت کرش کرد. لاگ را بررسی کنید: `logs/self_{uid}.log`"
                                    )
                                except Exception:
                                    pass

        except Exception as e:
            print(f"⚠️ خطا در watchdog: {e}")


# ═══════════════════════════════════════
# اجرای اصلی
# ═══════════════════════════════════════

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()

    print("=" * 50)
    print(f"🤖 ربات مدیریت سلف: @{me.username}")
    print(f"👑 مدیر اصلی: {ADMIN_ID}")
    print("=" * 50)
    print(f"📣 کاربران باید همین ربات را باز کنند:  t.me/{me.username}")
    print("📣 در تلگرام روی این لینک بزنید و /start را بفرستید.")
    print("📣 اگر /start جواب نداد، اینجا باید خط «📩 /start از ...» چاپ شود؛")
    print("📣 اگر چاپ نشد یعنی آپدیت به این پروسه نمی‌رسد (توکن مشترک / ربات اشتباه).")
    print("=" * 50)

    # اجرای خودکار سلف کاربران فعال (بعد از ری‌استارت ربات)
    started = 0
    for user in db.all_users():
        if user["status"] == STATUS_ACTIVE:
            if db.is_expired(user):
                db.expire(user["telegram_id"])
                continue
            if start_self_process(user):
                started += 1
    if started:
        print(f"♻️ {started} سلف فعال از قبل اجرا شد")

    asyncio.ensure_future(watchdog_loop())

    try:
        await bot.send_message(
            ADMIN_ID,
            "✅ **ربات مدیریت سلف روشن شد**\n"
            f"🤖 @{me.username}",
            buttons=[[Button.inline("👑 پنل مدیریت", data="admin_panel")]]
        )
    except Exception:
        pass

    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # بستن تمیز پروسه‌ها هنگام خاموش شدن
        for uid in list(RUNNING.keys()):
            stop_self_process(uid)
