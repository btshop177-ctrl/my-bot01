# ---------------------------------------------------------
# پچ مخصوص پایتون 3.10 تا 3.12 برای کتابخانه پایروگرام
import asyncio
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
# ---------------------------------------------------------

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)
from pyrogram.errors import FloodWait, ReactionInvalid, PeerIdInvalid, BadRequest
from datetime import datetime
import pytz
import json
import os
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

CONFIG_FILE = "config.json"

# ──────────────────────────────────────────────
#                    فونت‌ها
# ──────────────────────────────────────────────

FONT_MAP = {
    1: {"name": "🄁🄂:🄃🄄", "digits": "🄀🄁🄂🄃🄄🄅🄆🄇🄈🄉"},
    2: {"name": "𝟏𝟐:𝟑𝟒", "digits": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"},
    3: {"name": "ϩ𝟷:4Ϭ", "digits": "Ϭ𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    4: {"name": "¹²:³⁴", "digits": "⁰¹²³⁴⁵⁶⁷⁸⁹"},
    6: {"name": "❶❷:❸❹", "digits": "⓪❶❷❸❹❺❻❼❽❾"},
    7: {"name": "¹² ³⁴", "digits": "⁰¹²³⁴⁵⁶⁷⁸⁹", "separator": " "},
    8: {"name": "𝟷𝟸:𝟹𝟺", "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    9: {"name": "𝟭𝟮:𝟯𝟰", "digits": "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"},
    10: {"name": "𝟙𝟚:𝟛𝟜", "digits": "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"},
    11: {"name": "①②:③④", "digits": "⓪①②③④⑤⑥⑦⑧⑨"},
    12: {"name": "❶②:❸④", "digits": "⓪❶②❸④⑤❻⑦❽⑨"},
}

DEFAULT_CONFIG = {
    "clock_enabled": False,
    "clock_bio_enabled": False,
    "bio_text": "",
    "clock_font": 9,
    "reactions": [],
    "owner_id": None,
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            if k not in data:
                data[k] = v
        return data
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


config = load_config()
user_state = {}


def is_owner(uid):
    return uid == config.get("owner_id")


def get_fancy_time(font_id=None):
    if font_id is None:
        font_id = config.get("clock_font", 9)
    tz = pytz.timezone("Asia/Tehran")
    now = datetime.now(tz)
    ts = now.strftime("%H:%M")
    fi = FONT_MAP.get(font_id, FONT_MAP[9])
    d = fi["digits"]
    sep = fi.get("separator", ":")
    r = ""
    for c in ts:
        r += sep if c == ":" else d[int(c)]
    return f"⌥ {r}"


# ──────────────────────────────────────────────
#       کلاینت‌ها (بدون نیاز به شماره و پراکسی)
# ──────────────────────────────────────────────

user = Client(
    "user_session",
    api_id=api_id,
    api_hash=api_hash,
)

bot = Client(
    "bot_session",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
)


# ──────────────────────────────────────────────
#                 حلقه ساعت
# ──────────────────────────────────────────────

async def clock_loop():
    last = ""
    print("[CLOCK] ✅ موتور ساعت روشن شد")
    while True:
        try:
            if not config.get("clock_enabled") and not config.get("clock_bio_enabled"):
                await asyncio.sleep(5)
                continue
            cur = get_fancy_time()
            if cur != last:
                if config.get("clock_enabled"):
                    await user.update_profile(last_name=cur)
                if config.get("clock_bio_enabled") and config.get("bio_text"):
                    bio = f"{config['bio_text']} {cur}"[:70]
                    await user.update_profile(bio=bio)
                last = cur
            now = datetime.now()
            await asyncio.sleep(60 - now.second)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"[CLOCK] ❌ خطا: {e}")
            await asyncio.sleep(10)


# ──────────────────────────────────────────────
#                 حلقه ریکشن
# ──────────────────────────────────────────────

async def reaction_loop():
    print("[REACT] ✅ موتور ریکشن خودکار روشن شد")
    while True:
        try:
            active = [r for r in config.get("reactions", []) if r.get("enabled")]
            if not active:
                await asyncio.sleep(10)
                continue
            for item in active:
                cid = item["chat_id"]
                emoji = item.get("emoji", "👍")
                try:
                    async for msg in user.get_chat_history(cid, limit=1):
                        already = False
                        if msg.reactions and msg.reactions.reactions:
                            for rx in msg.reactions.reactions:
                                if getattr(rx, "chosen", False):
                                    already = True
                                    break
                        if not already:
                            try:
                                await user.send_reaction(cid, msg.id, emoji=emoji)
                                print(f"[REACT] ✅ {emoji} زده شد روی چت {cid}")
                            except (ReactionInvalid, BadRequest):
                                pass
                            except FloodWait as fw:
                                await asyncio.sleep(fw.value)
                except PeerIdInvalid:
                    pass
                except Exception as e:
                    print(f"[REACT] خطا روی {cid}: {e}")
                await asyncio.sleep(3)
            await asyncio.sleep(60)
        except Exception as e:
            print(f"[REACT] ❌ خطای کلی: {e}")
            await asyncio.sleep(15)


# ──────────────────────────────────────────────
#                 کیبوردها
# ──────────────────────────────────────────────

def main_kb():
    ck = "🟢" if config.get("clock_enabled") else "🔴"
    bk = "🟢" if config.get("clock_bio_enabled") else "🔴"
    fid = config.get("clock_font", 9)
    fn = FONT_MAP.get(fid, FONT_MAP[9])["name"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⏰ ساعت: {ck}", callback_data="toggle_clock")],
        [InlineKeyboardButton(f"📝 ساعت بیو: {bk}", callback_data="toggle_bio")],
        [InlineKeyboardButton("✏️ تنظیم متن بیو", callback_data="set_bio")],
        [InlineKeyboardButton(f"🔤 فونت: {fn}", callback_data="font_menu")],
        [InlineKeyboardButton("💬 ریکشن‌ها", callback_data="react_menu")],
        [InlineKeyboardButton("🔄 رفرش", callback_data="refresh")],
    ])


def font_kb():
    cur = config.get("clock_font", 9)
    btns = [[InlineKeyboardButton(
        f"{fid}: {fi['name']}{' ✅' if fid == cur else ''}",
        callback_data=f"font_{fid}"
    )] for fid, fi in sorted(FONT_MAP.items())]
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back")])
    return InlineKeyboardMarkup(btns)


def react_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن", callback_data="react_add")],
        [InlineKeyboardButton("📋 لیست", callback_data="react_list")],
        [InlineKeyboardButton("🗑 حذف", callback_data="react_del")],
        [InlineKeyboardButton("🧹 پاکسازی", callback_data="react_clear")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back")],
    ])


def react_list_kb():
    btns = [[InlineKeyboardButton(
        f"{'🟢' if r.get('enabled') else '🔴'} {r.get('emoji', '?')} → {r.get('chat_name', '?')}",
        callback_data=f"rtoggle_{i}"
    )] for i, r in enumerate(config.get("reactions", []))]
    if not btns:
        btns.append([InlineKeyboardButton("خالی ❌", callback_data="noop")])
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data="react_menu")])
    return InlineKeyboardMarkup(btns)


def back_kb(cb="back"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=cb)]])


def panel_txt():
    ck = "🟢" if config.get("clock_enabled") else "🔴"
    bk = "🟢" if config.get("clock_bio_enabled") else "🔴"
    fid = config.get("clock_font", 9)
    fn = FONT_MAP.get(fid, FONT_MAP[9])["name"]
    bio = config.get("bio_text") or "⚠️ خالی"
    total = len(config.get("reactions", []))
    act = len([r for r in config.get("reactions", []) if r.get("enabled")])
    return (
        f"🛠 **پنل مدیریت یوزربات**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⏰ ساعت: {ck}\n"
        f"📝 بیو: {bk}\n"
        f"🔤 فونت: `{fid}` — {fn}\n"
        f"🕐 نمونه: {get_fancy_time(fid)}\n"
        f"📄 متن: {bio}\n"
        f"💬 ریکشن: {act}/{total} فعال\n"
        f"━━━━━━━━━━━━━━━"
    )


# ──────────────────────────────────────────────
#            هندلرهای ربات
# ──────────────────────────────────────────────

@bot.on_message(filters.command(["start", "panel"]) & filters.private)
async def cmd_start(_, msg: Message):
    if not is_owner(msg.from_user.id):
        return await msg.reply("⛔ شما دسترسی ندارید.")
    user_state.clear()
    await msg.reply(panel_txt(), reply_markup=main_kb())


@bot.on_message(filters.text & filters.private & ~filters.command(["start", "panel"]))
async def handle_text(_, msg: Message):
    if not is_owner(msg.from_user.id):
        return
    state = user_state.get("state")
    text = msg.text.strip()

    if state == "waiting_bio":
        config["bio_text"] = text
        save_config(config)
        user_state.clear()
        return await msg.reply(f"✅ بیو تنظیم شد:\n`{text}`", reply_markup=back_kb())

    if state == "waiting_react_del":
        try:
            idx = int(text) - 1
            rlist = config.get("reactions", [])
            if 0 <= idx < len(rlist):
                rm = rlist.pop(idx)
                save_config(config)
                await msg.reply(f"✅ حذف شد: {rm.get('emoji')}", reply_markup=back_kb("react_menu"))
            else:
                await msg.reply("❌ شماره نامعتبر", reply_markup=back_kb("react_menu"))
        except:
            await msg.reply("❌ فقط عدد وارد کنید", reply_markup=back_kb("react_menu"))
        user_state.clear()
        return

    if state == "waiting_react_add" or text.startswith("ریکت"):
        t = text[len("ریکت"):].strip() if text.startswith("ریکت") else text
        parts = t.split(None, 1)
        if len(parts) < 2:
            return await msg.reply("❌ فرمت اشتباه! مثال: `ریکت ❤️ @user`", reply_markup=back_kb("react_menu"))
        emoji, target = parts[0], parts[1]
        try:
            cid = int(target) if target.lstrip("-").isdigit() else target
            chat = await user.get_chat(cid)
            config["reactions"].append({
                "chat_id": chat.id,
                "chat_name": getattr(chat, "title", None) or getattr(chat, "first_name", str(chat.id)),
                "emoji": emoji,
                "enabled": True,
            })
            save_config(config)
            user_state.clear()
            await msg.reply(f"✅ افزوده شد: {emoji} → {chat.id}", reply_markup=back_kb("react_menu"))
        except Exception as e:
            await msg.reply(f"❌ چت پیدا نشد: {e}", reply_markup=back_kb("react_menu"))
            user_state.clear()


@bot.on_callback_query()
async def handle_cb(_, cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    data = cb.data

    if data in ("back", "refresh"):
        user_state.clear()
        await cb.message.edit_text(panel_txt(), reply_markup=main_kb())
        return await cb.answer("🔄")

    if data == "toggle_clock":
        config["clock_enabled"] = not config["clock_enabled"]
        save_config(config)
        if not config["clock_enabled"]:
            try:
                await user.update_profile(last_name="")
            except:
                pass
        await cb.message.edit_text(panel_txt(), reply_markup=main_kb())
        return await cb.answer("✅ روشن" if config["clock_enabled"] else "❌ خاموش")

    if data == "toggle_bio":
        if not config.get("bio_text"):
            return await cb.answer("❌ اول بیو تنظیم کن!", show_alert=True)
        config["clock_bio_enabled"] = not config["clock_bio_enabled"]
        save_config(config)
        if not config["clock_bio_enabled"]:
            try:
                await user.update_profile(bio=config.get("bio_text", ""))
            except:
                pass
        await cb.message.edit_text(panel_txt(), reply_markup=main_kb())
        return await cb.answer()

    if data == "set_bio":
        user_state["state"] = "waiting_bio"
        await cb.message.edit_text("📝 متن بیو جدید را بفرستید:", reply_markup=back_kb())
        return await cb.answer()

    if data == "font_menu":
        await cb.message.edit_text("🔤 فونت را انتخاب کنید:", reply_markup=font_kb())
        return await cb.answer()

    if data.startswith("font_"):
        fid = int(data[5:])
        config["clock_font"] = fid
        save_config(config)
        await cb.message.edit_text(panel_txt(), reply_markup=main_kb())
        return await cb.answer(get_fancy_time(fid))

    if data == "react_menu":
        user_state.clear()
        await cb.message.edit_text("💬 مدیریت ریکشن‌ها:", reply_markup=react_kb())
        return await cb.answer()

    if data == "react_add":
        user_state["state"] = "waiting_react_add"
        await cb.message.edit_text("➕ بفرستید: `ریکت ❤️ @user`", reply_markup=back_kb("react_menu"))
        return await cb.answer()

    if data == "react_list":
        await cb.message.edit_text("📋 لیست (برای خاموش/روشن کلیک کنید):", reply_markup=react_list_kb())
        return await cb.answer()

    if data.startswith("rtoggle_"):
        idx = int(data[8:])
        rlist = config.get("reactions", [])
        if 0 <= idx < len(rlist):
            rlist[idx]["enabled"] = not rlist[idx].get("enabled", True)
            save_config(config)
        await cb.message.edit_text("📋 لیست:", reply_markup=react_list_kb())
        return await cb.answer()

    if data == "react_del":
        rlist = config.get("reactions", [])
        if not rlist:
            return await cb.answer("خالی است!", show_alert=True)
        user_state["state"] = "waiting_react_del"
        txt = "\n".join(f"`{i+1}` {r.get('emoji')} → {r.get('chat_name')}" for i, r in enumerate(rlist))
        await cb.message.edit_text(f"🗑 شماره ریکشن را بفرستید:\n{txt}", reply_markup=back_kb("react_menu"))
        return await cb.answer()

    if data == "react_clear":
        config["reactions"] = []
        save_config(config)
        await cb.message.edit_text("💬 مدیریت ریکشن‌ها:", reply_markup=react_kb())
        return await cb.answer("🧹 تمام ریکشن‌ها پاک شد!", show_alert=True)

    await cb.answer()


@user.on_message(filters.me & filters.regex(r"^پنل$"))
async def user_panel(_, msg: Message):
    try:
        b = await bot.get_me()
        await msg.edit_text(f"🛠 پنل:\n👉 t.me/{b.username}")
    except:
        pass


# ──────────────────────────────────────────────
#              🔥 اجرای اصلی
# ──────────────────────────────────────────────

async def main():
    print("=" * 45)
    print("  🚀 در حال راه‌اندازی (بدون پراکسی)...")
    print("=" * 45)

    print("\n📱 در حال اتصال یوزربات...")
    await user.start()
    me = await user.get_me()
    print(f"  ✅ @{me.username or me.first_name}")

    print("\n🤖 در حال اتصال ربات...")
    await bot.start()
    bot_me = await bot.get_me()
    print(f"  ✅ @{bot_me.username}")

    config["owner_id"] = me.id
    save_config(config)

    print("\n" + "=" * 45)
    print(f"  📌 لینک پنل: https://t.me/{bot_me.username}")
    print("=" * 45)

    # اجرای تسک‌های پس‌زمینه
    asyncio.create_task(clock_loop())
    asyncio.create_task(reaction_loop())

    print("\n  ⏳ ربات روشن شد... (برای توقف در ترمینال Ctrl+C را بزنید)\n")

    # منتظر ماندن اسکریپت برای همیشه
    stop_event = asyncio.Event()
    await stop_event.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 متوقف شد")