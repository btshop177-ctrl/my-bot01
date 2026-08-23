"""
سلف‌بات حرفه‌ای تلگرام
تمام دستورات از چت خودتان انجام می‌شود
"""

import asyncio
import json
import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from clock import ClockManager
from reaction import ReactionManager
from banner import BannerManager
from effects import EffectManager, AVAILABLE_EFFECTS
from spam import SpamManager
from bot import BotManager
from panel import set_bot_username
from panel_tracker import PanelTracker
from action import ActionManager, ACTION_MAP, ACTION_DESC
from werewolf import get_training_response, is_training_command
from werewolf_game import (
    WerewolfGameManager,
    VALID_TARGET_RE,
    is_vote_registration,
    parse_vote_index_command,
)

load_dotenv()

# ─── تنظیمات ───
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ─── پروکسی ───
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
        print("⚠️ نصب کنید: pip install python-socks[asyncio]")
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


CONFIG_FILE = "config.json"


class ConfigManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.data = self._load()

    def _load(self):
        defaults = {
            "clock_enabled": False,
            "clock_bio_enabled": False,
            "bio_text": "",
            "clock_font": 9,
            "user_reactions": [],
            "chat_reactions": [],
            "text_reactions": [],
            "tapchi_enabled": False,
            "banner_mode": "forward",
            "banners": {},
            "active_effects": [],
            "open_panels": [],
            "owner_id": 0,
            "actions_list": [],
            "werewolf_vote_enabled": False,
            "werewolf_votes": [],
            "werewolf_game_votes": {},
            "werewolf_next_group_id": None,
            "werewolf_next_group_ids": [],
        }
        if os.path.exists(self.filepath):
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, val in defaults.items():
                    data.setdefault(key, val)
                return data
        return defaults

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()


# ═══════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════

def extract_name(entity):
    if hasattr(entity, 'title') and entity.title:
        return entity.title
    first = getattr(entity, 'first_name', '') or ''
    last = getattr(entity, 'last_name', '') or ''
    name = f"{first} {last}".strip()
    if name:
        return name
    username = getattr(entity, 'username', '')
    if username:
        return f"@{username}"
    return str(entity.id)


def is_user_entity(entity):
    return hasattr(entity, 'first_name') and not hasattr(entity, 'title')


def format_user_info(entity):
    if hasattr(entity, 'title') and entity.title:
        name = entity.title
        entity_type = "چت/کانال"
    else:
        first = getattr(entity, 'first_name', '') or ''
        last = getattr(entity, 'last_name', '') or ''
        name = f"{first} {last}".strip() or "بدون نام"
        entity_type = "کاربر"

    username = getattr(entity, 'username', None)
    user_id = entity.id

    lines = [f"👤 **{entity_type}**\n"]
    lines.append(f"  ▸ **نام:** {name}")
    if username:
        lines.append(f"  ▸ **یوزرنیم:** @{username}")
    else:
        lines.append(f"  ▸ **یوزرنیم:** ندارد")
    lines.append(f"  ▸ **آیدی عددی:** `{user_id}`")
    if username:
        lines.append(f"  ▸ **لینک:** t.me/{username}")

    if entity_type == "کاربر":
        if getattr(entity, 'bot', False):
            lines.append(f"  ▸ **نوع:** 🤖 ربات")
        if getattr(entity, 'premium', False):
            lines.append(f"  ▸ **پرمیوم:** ✅")
        if getattr(entity, 'verified', False):
            lines.append(f"  ▸ **تایید شده:** ✅")

    return "\n".join(lines)


# ═══════════════════════════════════════
# توابع تشخیص دقیق دستور
# ═══════════════════════════════════════

def _looks_like_id_or_username(text):
    if not text:
        return False
    if " " in text:
        return False
    if text.lstrip("-").isdigit():
        return True
    if text.startswith("@"):
        username = text[1:]
        if username and all(c.isalnum() or c == "_" for c in username):
            return True
        return False
    if all(c.isalnum() or c == "_" for c in text):
        if 5 <= len(text) <= 32:
            if any(c.isalpha() for c in text):
                if all(ord(c) < 128 for c in text):
                    return True
    return False


def _looks_like_emoji(text):
    if not text:
        return False
    if len(text) > 8:
        return False
    for c in text:
        if 'a' <= c.lower() <= 'z':
            return False
        if '\u0600' <= c <= '\u06FF' or '\uFB50' <= c <= '\uFDFF':
            return False
        if '\u06F0' <= c <= '\u06F9':
            return False
        if '0' <= c <= '9':
            return False
    return True


def _is_valid_effect_command(rest):
    if not rest:
        return False
    if rest.endswith(" روشن"):
        effect_name = rest[:-5].strip()
    elif rest.endswith(" خاموش"):
        effect_name = rest[:-6].strip()
    else:
        return False
    if not effect_name:
        return False
    return effect_name in AVAILABLE_EFFECTS


def _is_valid_action_type(name):
    return name in ACTION_MAP


def is_command(text):
    if not text:
        return False

    # ─── دستورات دقیق ───
    exact_commands = {
        "پنل",
        "بستن پنل", "بستن پنل ها", "بستن پنلها", "بستن همه پنل",
        "ساعت روشن", "ساعت خاموش", "ساعت بیو روشن", "ساعت بیو خاموش",
        "آیدی", "ایدی", "id", "ID", "Id",
        "تپچی روشن", "تپچی خاموش",
        "حالت بنر فور", "حالت بنر کپی",
        "لیست بنر", "لیست کل بنر", "لیست کامل بنر",
        "پاکسازی لیست بنر", "پاکسازی کل تپچی",
        "لیست افکت", "پاکسازی افکت",
        "لیست ریکت", "پاکسازی ریکت",
        "حذف ریکت", "پاک ریکت",
        "اسپم توقف", "توقف اسپم", "اسپم خاموش",
        "پاکسازی اسپم", "اسپم پاکسازی",
        "لیست اسپم", "اسپم لیست",
        "لیست کل اسپم", "لیست اسپم ها", "اسپم های فعال",
        "اکشن روشن", "اکشن خاموش",
        "لیست اکشن", "پاکسازی اکشن",
        "حذف اکشن",
        "وضعیت روستا", "وضعيت روستا",
        "رای", "رای روشن", "رای خاموش",
        "گرگینه اینجا", "گرگینه حذف",
        "نکست", "next", "لغو نکست", "/nextgame@werewolfbot",
        "/startgame", "/startchaos",
        "/startgame@werewolfbot", "/startchaos@werewolfbot",
        "راهنما",
    }

    if text in exact_commands:
        return True

    # ─── آموزش نقش‌های گرگینه ───
    if is_training_command(text):
        return True

    # ─── رأی خودکار گرگینه ───
    if is_vote_registration(text):
        return True
    if parse_vote_index_command(text, "حذف رای") is not None:
        return True
    if parse_vote_index_command(text, "تغییر رای") is not None:
        return True

    # ─── اکشن [نوع] ───
    if text.startswith("اکشن "):
        rest = text[len("اکشن "):].strip()
        if rest in ACTION_MAP:
            return True
        return False

    # ─── حذف اکشن [شماره] ───
    if text.startswith("حذف اکشن "):
        rest = text[len("حذف اکشن "):].strip()
        if rest.isdigit():
            return True
        return False

    # ─── حالت اکشن [نوع] ───
    if text.startswith("حالت اکشن "):
        rest = text[len("حالت اکشن "):].strip()
        if _is_valid_action_type(rest):
            return True
        return False

    # ─── بیو ───
    if text.startswith("بیو "):
        rest = text[4:].strip()
        if len(rest.split()) <= 10:
            return True
        return False

    # ─── فونت ساعت ───
    if text.startswith("فونت ساعت "):
        rest = text[10:].strip()
        if rest.isdigit():
            num = int(rest)
            if 1 <= num <= 12:
                return True
        return False

    # ─── افکت ───
    if text.startswith("افکت "):
        rest = text[5:].strip()
        if _is_valid_effect_command(rest):
            return True
        return False

    # ─── آیدی ───
    id_prefixes = ("آیدی ", "ایدی ", "id ", "ID ", "Id ")
    for prefix in id_prefixes:
        if text.startswith(prefix):
            rest = text[len(prefix):].strip()
            if _looks_like_id_or_username(rest):
                return True
            return False

    # ─── بنر ───
    if text.startswith("بنر "):
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return True
        return False

    # ─── حذف بنر ───
    if text.startswith("پاک کردن بنر ") or text.startswith("حذف بنر "):
        parts = text.split()
        if len(parts) >= 3 and parts[-1].isdigit():
            return True
        return False

    # ─── ریکت متن ───
    if text.startswith("ریکت متن "):
        parts = text.split(maxsplit=3)
        # ریکت متن [ایموجی] [کلمه]
        if len(parts) >= 4:
            if _looks_like_emoji(parts[2]):
                return True
        return False

    # ─── حذف ریکت متن ───
    if text.startswith("حذف ریکت متن "):
        rest = text[14:].strip()
        if rest:
            return True
        return False

    # ─── ریکت اینجا / ریکت چت ───
    if text.startswith("ریکت اینجا ") or text.startswith("ریکت چت "):
        parts = text.split(maxsplit=2)
        if len(parts) >= 3:
            emoji_part = parts[2].strip()
            if _looks_like_emoji(emoji_part):
                return True
        return False

    # ─── ریکت ───
    if text.startswith("ریکت "):
        parts = text.split(maxsplit=2)
        if len(parts) >= 2:
            if _looks_like_emoji(parts[1]):
                return True
        return False

    # ─── حذف ریکت ───
    if text.startswith("حذف ریکت "):
        rest = text[9:].strip()
        if _looks_like_id_or_username(rest):
            return True
        if rest.isdigit():
            return True
        return False

    # ─── اسپم توقف ───
    if text.startswith("اسپم توقف "):
        rest = text[10:].strip()
        if rest == "همه" or rest.isdigit():
            return True
        return False

    if text.startswith("توقف اسپم "):
        rest = text[10:].strip()
        if rest == "همه" or rest.isdigit():
            return True
        return False

    # ─── اسپم ───
    if text.startswith("اسپم "):
        rest = text[5:].strip()

        if rest.startswith("حذفی "):
            after = rest[5:].strip()
            parts = after.split()
            if len(parts) >= 2:
                try:
                    delay = float(parts[0])
                    if delay >= 1:
                        return True
                except ValueError:
                    pass
            return False

        parts = rest.split()
        if len(parts) >= 2:
            try:
                delay = float(parts[0])
                if delay >= 1:
                    return True
            except ValueError:
                pass
        return False

    return False


def _parse_target_from_parts(parts):
    """
    از آخر پارامترها تارگت رو استخراج کن
    برمیگرداند: (target_str, remaining_parts)
    """
    if not parts:
        return None, parts

    last = parts[-1]

    # اگر آخری یوزرنیم یا آیدی عددی باشه → تارگت
    if last.startswith("@") and len(last) > 1:
        return last, parts[:-1]

    if last.lstrip("-").isdigit() and len(parts) > 1:
        # مطمئن شو عدد بزرگه (آیدی) نه عدد کوچک (تعداد)
        num = int(last.lstrip("-"))
        if num > 1000:
            return last, parts[:-1]

    return None, parts


def _parse_text_trigger(parts):
    """
    بررسی وجود متن‌خاص: در پارامترها
    برمیگرداند: (trigger_keyword, remaining_parts)
    """
    for i, part in enumerate(parts):
        if part.startswith("متن‌خاص:") or part.startswith("متن‌خاص:"):
            keyword = part.split(":", 1)[1] if ":" in part else ""
            if keyword:
                remaining = parts[:i] + parts[i + 1:]
                return keyword, remaining
    return None, parts


async def _parse_and_start_spam(spam_mgr, event, text, delete_mode,
                                user_client=None):
    """پارس دستور اسپم و شروع اسپم جدید"""
    if not text:
        return (
            "❌ **فرمت اشتباه**\n\n"
            "**فرمت‌های اسپم:**\n"
            "`اسپم [تاخیر] [متن]`\n"
            "`اسپم [تاخیر] [متن] [تعداد]`\n"
            "`اسپم [تاخیر] [متن] @target`\n"
            "`اسپم [تاخیر] [متن] [تعداد] @target`\n"
            "`اسپم حذفی [تاخیر] [متن]`\n"
            "`اسپم [تاخیر] [متن] متن‌خاص:[کلمه]`\n\n"
            "ریپلای + اسپم → اسپم ریپلای\n\n"
            "**مثال‌ها:**\n"
            "`اسپم 3 سلام`\n"
            "`اسپم 5 hello 20`\n"
            "`اسپم 3 سلام @username`\n"
            "`اسپم حذفی 3 test`\n"
            "`اسپم 3 پاسخ متن‌خاص:سلام`"
        )

    parts = text.split()
    if len(parts) < 2:
        return "❌ **فرمت نامعتبر**\nحداقل: `اسپم [تاخیر] [متن]`"

    try:
        delay = float(parts[0])
    except ValueError:
        return "❌ **تاخیر باید عدد باشد**"

    MIN_DELAY = 2.3
    if delay < MIN_DELAY:
        return f"❌ **تاخیر خیلی کم**\nحداقل: `{MIN_DELAY}` ثانیه"

    remaining = parts[1:]

    # بررسی متن‌خاص (تریگر)
    trigger_keyword, remaining = _parse_text_trigger(remaining)

    # بررسی تارگت
    target_str, remaining = _parse_target_from_parts(remaining)

    # بررسی تعداد
    count = None
    if len(remaining) > 1:
        try:
            possible_count = int(remaining[-1])
            if 0 < possible_count < 1000:
                count = possible_count
                remaining = remaining[:-1]
        except ValueError:
            pass

    spam_text = " ".join(remaining)
    if not spam_text:
        return "❌ **متن اسپم خالی است**"

    # ─── ریپلای ───
    reply_to = None
    if event.is_reply:
        reply = await event.get_reply_message()
        reply_to = reply.id

    # ─── اسپم متنی (تریگر) ───
    if trigger_keyword:
        ts_id = spam_mgr.add_text_spam(
            keyword=trigger_keyword,
            text=spam_text,
            delay=delay,
            count=count
        )
        try:
            await event.delete()
        except:
            pass
        count_text = f"{count} بار" if count else "بی‌نهایت ∞"
        print(
            f"✅ اسپم متنی [{ts_id}] | تریگر: {trigger_keyword} | "
            f"تاخیر: {delay}s | {count_text}"
        )
        return None

    # ─── اسپم تارگتی ───
    if target_str:
        target_id = None
        target_name = target_str
        if user_client:
            try:
                if target_str.lstrip("-").isdigit():
                    target_id = int(target_str)
                    try:
                        entity = await user_client.get_entity(target_id)
                        target_name = extract_name(entity)
                    except:
                        target_name = str(target_id)
                else:
                    entity = await user_client.get_entity(target_str)
                    target_id = entity.id
                    target_name = extract_name(entity)
            except Exception as e:
                return f"❌ **تارگت پیدا نشد:** {str(e)[:60]}"

        if not target_id:
            return "❌ **تارگت نامعتبر**"

        try:
            entity = await user_client.get_entity(event.chat_id)
            chat_name = extract_name(entity)
        except:
            chat_name = str(event.chat_id)

        ts_id = spam_mgr.add_target_spam(
            chat_id=event.chat_id,
            target_id=target_id,
            text=spam_text,
            delay=delay,
            count=count,
            chat_name=chat_name,
            target_name=target_name,
        )

        try:
            await event.delete()
        except:
            pass

        count_text = f"{count} بار" if count else "بی‌نهایت ∞"
        print(
            f"✅ اسپم تارگتی [{ts_id}] | تارگت: {target_name} | "
            f"تاخیر: {delay}s | {count_text}"
        )
        return None

    # ─── اسپم عادی ───
    try:
        await event.delete()
    except:
        pass

    spam_id = await spam_mgr.start_spam(
        chat_id=event.chat_id,
        text=spam_text,
        delay=delay,
        count=count,
        delete=delete_mode,
        reply_to=reply_to,
    )

    mode_text = "حذفی 🗑" if delete_mode else "معمولی 📤"
    count_text = f"{count} بار" if count else "بی‌نهایت ∞"
    reply_text = " | ریپلای" if reply_to else ""
    print(
        f"✅ اسپم [{spam_id}] شروع شد | {mode_text} | "
        f"تاخیر: {delay}s | {count_text}{reply_text}"
    )

    return None


# ─── ساخت کلاینت‌ها ───
proxy_config = build_proxy()

if proxy_config:
    print(f"🌐 پروکسی: {PROXY_SCHEME}://{PROXY_HOST}:{PROXY_PORT}")
    user_client = TelegramClient(
        "user_session", API_ID, API_HASH,
        proxy=proxy_config,
        connection_retries=5, retry_delay=2,
        timeout=30, auto_reconnect=True,
    )
    bot_client = TelegramClient(
        "bot_session", API_ID, API_HASH,
        proxy=proxy_config,
        connection_retries=5, retry_delay=2,
        timeout=30, auto_reconnect=True,
    )
else:
    print("🔌 بدون پروکسی")
    user_client = TelegramClient("user_session", API_ID, API_HASH)
    bot_client = TelegramClient("bot_session", API_ID, API_HASH)


async def main():
    await user_client.start(phone=PHONE_NUMBER)
    await bot_client.start(bot_token=BOT_TOKEN)

    print("✅ یوزر کلاینت متصل شد")
    print("✅ ربات متصل شد")

    me = await user_client.get_me()
    owner_id = me.id

    bot_me = await bot_client.get_me()
    bot_username = bot_me.username
    set_bot_username(bot_username)

    print(f"👤 Owner: {me.first_name} ({owner_id})")
    print(f"🤖 Bot: @{bot_username}")

    config = ConfigManager(CONFIG_FILE)
    config.set("owner_id", owner_id)

    # ─── ساخت ماژول‌ها ───
    clock = ClockManager(user_client, config)
    react = ReactionManager(user_client, config)
    banner = BannerManager(user_client, config)
    effects = EffectManager(user_client, config)
    spam = SpamManager(user_client, effects, config)
    panel_tracker = PanelTracker(config)
    action = ActionManager(user_client, config)
    owner_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
    werewolf_game = WerewolfGameManager(
        user_client,
        config,
        owner_id,
        owner_names=(owner_full_name, me.first_name, me.username),
    )

    # ─── استارت اکشن‌های ذخیره شده ───
    action.start_saved_actions()

    # ─── استارت ماژول‌ها ───
    if config.get("clock_enabled"):
        clock.start()
        print("⏰ ساعت از تنظیمات قبلی روشن شد")

    if config.get("tapchi_enabled"):
        banner.start_all()
        print("📢 تپچی از تنظیمات قبلی روشن شد")

    # ─── ساخت مدیر ربات ───
    bot_mgr = BotManager(
        bot_client, config, clock, react, banner, spam,
        panel_tracker, owner_id, action_mgr=action,
        werewolf_mgr=werewolf_game
    )

    # ═══════════════════════════════════════
    # هندلر پنل
    # ═══════════════════════════════════════
    @user_client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^پنل$"))
    async def panel_command(event):
        try:
            await event.delete()
            results = await user_client.inline_query(bot_username, "panel")
            sent_msg = await results[0].click(
                event.chat_id,
                reply_to=event.reply_to_msg_id if event.is_reply else None,
                hide_via=False
            )
            if sent_msg:
                panel_tracker.add_panel(event.chat_id, sent_msg.id)
        except Exception as e:
            print(f"❌ خطا در باز کردن پنل: {e}")
            await user_client.send_message(
                event.chat_id,
                f"❌ خطا: `{e}`\nInline Mode ربات روشن است؟"
            )

    # ═══════════════════════════════════════
    # هندلر ریکت + اکشن + اسپم متنی (پیام‌های ورودی)
    # ═══════════════════════════════════════
    @user_client.on(events.NewMessage(incoming=True))
    async def incoming_handler(event):
        # پیام‌ها و منوهای ربات رسمی گرگینه
        await werewolf_game.handle_bot_message(event)

        # پاسخ عمومی وضعیت فقط در گروه بازی فعال
        incoming_text = event.raw_text.strip() if event.raw_text else ""
        if (incoming_text in ("وضعیت روستا", "وضعيت روستا")
                and werewolf_game.is_tracked_group(event.chat_id)):
            await event.reply(
                werewolf_game.get_village_status(event.chat_id)
            )

        # ریکت خودکار
        await react.handle_new_message(event)

        # اسپم متنی (تریگر)
        await spam.handle_text_trigger(event)

        # اسپم تارگتی
        await spam.handle_target_trigger(event)

    @user_client.on(events.MessageEdited(incoming=True))
    async def werewolf_edited_handler(event):
        # صلح‌گرا و اتمام مهلت، متن منوی خصوصی را ویرایش می‌کنند.
        await werewolf_game.handle_bot_message(event, edited=True)

    # ═══════════════════════════════════════
    # هندلر همه دستورات
    # ═══════════════════════════════════════
    @user_client.on(events.NewMessage(outgoing=True))
    async def commands_handler(event):
        text = event.raw_text.strip() if event.raw_text else ""
        if not text:
            return

        # دستورات واقعی شروع را فقط علامت‌گذاری می‌کنیم تا پیام نزدیک ربات
        # و لیست #players همان گروه پیدا شود؛ خود دستور دست‌نخورده می‌ماند.
        if text.lower() in (
            "/startchaos", "/startchaos@werewolfbot",
            "/startgame", "/startgame@werewolfbot",
        ):
            await werewolf_game.handle_bot_message(event)
            return

        # ═══════════════════════════════════════
        # مدیریت گروه‌های بازی و رأی از چت
        # ═══════════════════════════════════════
        if text == "گرگینه اینجا":
            if not event.is_group:
                await event.edit("❌ این دستور فقط داخل گروه قابل استفاده است.")
            else:
                await event.edit(
                    werewolf_game.track_group_manually(event.chat_id)
                )
            return

        if text == "گرگینه حذف":
            await event.edit(werewolf_game.untrack_group(event.chat_id))
            return

        if text == "رای روشن":
            await event.edit(werewolf_game.enable_votes())
            return

        if text == "رای خاموش":
            await event.edit(werewolf_game.disable_votes())
            return

        # ═══════════════════════════════════════
        # انتظار بازی بعدی و ورود خودکار
        # ═══════════════════════════════════════
        if text in ("نکست", "next"):
            if not event.is_group:
                await event.edit("❌ دستور نکست را داخل گروه موردنظر بنویسید.")
                return
            werewolf_game.set_next_wait(event.chat_id)
            await event.delete()
            await user_client.send_message(event.chat_id, "/nextgame@werewolfbot")
            return

        if text == "لغو نکست":
            group_id = event.chat_id if event.is_group else None
            success, result = await werewolf_game.cancel_next_wait(group_id)
            icon = "✅" if success else "❌"
            await event.edit(f"{icon} نکست: {result}")
            return

        # ═══════════════════════════════════════
        # وضعیت احتمالی بازی گرگینه
        # ═══════════════════════════════════════
        if text in ("وضعیت روستا", "وضعيت روستا"):
            await event.edit(
                werewolf_game.get_village_status(event.chat_id)
            )
            return

        async def resolve_vote_target(target_text="", reply=None):
            if reply and reply.sender_id:
                entity = await user_client.get_entity(reply.sender_id)
                return entity.id, extract_name(entity)
            target_text = target_text.strip()
            if target_text.isdigit():
                # برای آیدی عددی access_hash لازم نیست؛ خود دکمه با ID پیدا می‌شود.
                return int(target_text), target_text
            entity = await user_client.get_entity(target_text)
            return entity.id, extract_name(entity)

        # حذف رأی با شمارهٔ ترتیبی
        remove_index = parse_vote_index_command(text, "حذف رای")
        if remove_index is not None:
            await event.edit(
                werewolf_game.remove_vote(event.chat_id, remove_index)
            )
            return

        # تغییر رأی با شماره؛ هدف یا آرگومان است یا ریپلای.
        change_index = parse_vote_index_command(text, "تغییر رای")
        if change_index is not None:
            parts = text.split(maxsplit=3)
            target_text = parts[3].strip() if len(parts) == 4 else ""
            reply = await event.get_reply_message() if event.is_reply else None
            if not ((reply and text == f"تغییر رای {change_index}")
                    or (not reply and VALID_TARGET_RE.fullmatch(target_text))):
                await event.edit(
                    "❌ فرمت: تغییر رای 2 @username\n"
                    "یا «تغییر رای 2» را روی پیام شخص ریپلای کنید."
                )
                return
            try:
                target_id, target_name = await resolve_vote_target(
                    target_text, reply
                )
                await event.edit(werewolf_game.change_vote(
                    event.chat_id, change_index, target_id, target_name
                ))
            except Exception as e:
                await event.edit(f"❌ شخص پیدا نشد: {str(e)[:80]}")
            return

        # فقط «رای» خالیِ ریپلای‌شده یا «رای ID/@username» معتبر است.
        if is_vote_registration(text, event.is_reply):
            if not werewolf_game.is_vote_enabled():
                await event.edit(
                    "❌ رأی خودکار خاموش است؛ «رای روشن» را بزنید."
                )
                return
            reply = await event.get_reply_message() if event.is_reply else None
            target_text = text[4:].strip() if not event.is_reply else ""
            try:
                target_id, target_name = await resolve_vote_target(
                    target_text, reply
                )
                result = await werewolf_game.register_vote(
                    event.chat_id, target_id, target_name
                )
                await event.edit(result)
            except Exception as e:
                await event.edit(f"❌ شخص پیدا نشد: {str(e)[:80]}")
            return

        # ═══════════════════════════════════════
        # دانشنامهٔ نقش‌های گرگینه
        # ═══════════════════════════════════════
        training_response = get_training_response(text)
        if training_response is not None:
            try:
                await event.edit(training_response, parse_mode=None)
            except Exception as e:
                print(f"❌ خطا در نمایش آموزش نقش: {e}")
                try:
                    await event.respond(training_response, parse_mode=None)
                    await event.delete()
                except Exception:
                    pass
            return

        # ═══════════════════════════════════════
        # بستن پنل‌ها
        # ═══════════════════════════════════════
        if text == "بستن پنل":
            await event.delete()
            closed, failed = await panel_tracker.close_panels_in_chat(
                user_client, event.chat_id
            )
            if closed == 0 and failed == 0:
                msg = await user_client.send_message(
                    event.chat_id, "📭 **در این چت پنل بازی نیست**"
                )
            else:
                text_result = f"✅ **{closed} پنل در این چت بسته شد**"
                if failed > 0:
                    text_result += f"\n⚠️ {failed} پنل حذف نشد"
                msg = await user_client.send_message(event.chat_id, text_result)
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except:
                pass
            return

        elif text in ("بستن پنل ها", "بستن پنلها", "بستن همه پنل"):
            await event.delete()
            closed, failed = await panel_tracker.close_all_panels(user_client)
            if closed == 0 and failed == 0:
                msg = await user_client.send_message(
                    event.chat_id, "📭 **هیچ پنل بازی وجود ندارد**"
                )
            else:
                text_result = (f"✅ **بسته شدن پنل‌ها**\n\n"
                              f"  ▸ بسته شده: `{closed}`\n"
                              f"  ▸ ناموفق: `{failed}`")
                msg = await user_client.send_message(event.chat_id, text_result)
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except:
                pass
            return

        # ═══════════════════════════════════════
        # راهنما
        # ═══════════════════════════════════════
        elif text == "راهنما":
            try:
                await event.delete()
                results = await user_client.inline_query(bot_username, "panel")
                sent_msg = await results[0].click(
                    event.chat_id, hide_via=False
                )
                if sent_msg:
                    panel_tracker.add_panel(event.chat_id, sent_msg.id)
            except:
                from panel import get_help_panel_text
                await event.edit(get_help_panel_text())
            return

        # ═══════════════════════════════════════
        # دستورات ساعت
        # ═══════════════════════════════════════
        elif text == "ساعت روشن":
            config.set("clock_enabled", True)
            clock.start()
            await event.edit("✅ **ساعت روشن شد**")
            return

        elif text == "ساعت خاموش":
            config.set("clock_enabled", False)
            clock.stop()
            await event.edit("🔴 **ساعت خاموش شد**")
            return

        elif text == "ساعت بیو روشن":
            if not config.get("bio_text"):
                await event.edit(
                    "❌ **ابتدا متن بیو را تنظیم کنید:**\n`بیو [متن]`"
                )
                return
            config.set("clock_bio_enabled", True)
            await event.edit("✅ **ساعت بیو روشن شد**")
            return

        elif text == "ساعت بیو خاموش":
            config.set("clock_bio_enabled", False)
            await event.edit("🔴 **ساعت بیو خاموش شد**")
            return

        elif text.startswith("بیو ") and is_command(text):
            bio = text[4:].strip()
            if bio:
                config.set("bio_text", bio)
                await event.edit(f"✅ **متن بیو تنظیم شد:**\n`{bio}`")
            return

        elif text.startswith("فونت ساعت ") and is_command(text):
            try:
                font_id = int(text.replace("فونت ساعت", "").strip())
                if font_id < 1 or font_id > 12:
                    await event.edit("❌ **شماره فونت بین 1 تا 12**")
                    return
                config.set("clock_font", font_id)
                clock.last_time = ""
                from fonts import FONT_MAP
                await event.edit(
                    f"✅ **فونت تغییر کرد**\n"
                    f"فونت: `{font_id}` ▸ {FONT_MAP[font_id]['name']}"
                )
            except ValueError:
                await event.edit("❌ **فرمت اشتباه**\nمثال: `فونت ساعت 3`")
            return

        # ═══════════════════════════════════════
        # دستورات اکشن
        # ═══════════════════════════════════════
        elif text == "اکشن روشن":
            result = action.enable_action(event.chat_id)
            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش اکشن روشن: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        elif text == "اکشن خاموش":
            result = action.disable_action(event.chat_id)
            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش اکشن خاموش: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        elif text.startswith("حالت اکشن ") and is_command(text):
            action_type = text[len("حالت اکشن "):].strip()
            chat_id = event.chat_id
            try:
                entity = await user_client.get_entity(chat_id)
                chat_name = extract_name(entity)
            except:
                chat_name = str(chat_id)

            result = action.add_action(chat_id, action_type, chat_name)

            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش حالت اکشن: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        elif text.startswith("اکشن ") and is_command(text):
            action_type = text[len("اکشن "):].strip()
            chat_id = event.chat_id
            try:
                entity = await user_client.get_entity(chat_id)
                chat_name = extract_name(entity)
            except:
                chat_name = str(chat_id)

            result = action.add_action(chat_id, action_type, chat_name)

            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش اکشن add: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        elif text == "حذف اکشن":
            result = action.remove_action(event.chat_id)
            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش حذف اکشن: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        elif text.startswith("حذف اکشن ") and is_command(text):
            rest = text[len("حذف اکشن "):].strip()

            if rest.isdigit():
                result = action.remove_by_index(int(rest))
            else:
                result = "❌ **فرمت اشتباه**\n`حذف اکشن [شماره]`"

            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش حذف اکشن شماره: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        elif text == "لیست اکشن":
            result = action.get_list_text()
            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش لیست اکشن: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        elif text == "پاکسازی اکشن":
            result = action.clear_all()
            try:
                await event.edit(result)
            except Exception as e:
                print(f"❌ ویرایش پاکسازی اکشن: {e}")
                try:
                    await event.respond(result)
                    await event.delete()
                except:
                    pass
            return

        # ═══════════════════════════════════════
        # دستور آیدی
        # ═══════════════════════════════════════
        elif text in ("آیدی", "ایدی", "id", "ID", "Id"):
            target_entity = None
            if event.is_reply:
                reply = await event.get_reply_message()
                if reply.sender_id:
                    try:
                        target_entity = await user_client.get_entity(
                            reply.sender_id
                        )
                    except:
                        pass
            if not target_entity:
                target_entity = await user_client.get_me()
            info = format_user_info(target_entity)
            await event.edit(info)
            return

        elif text.startswith(
            ("آیدی ", "ایدی ", "id ", "ID ", "Id ")
        ) and is_command(text):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                return
            target = parts[1].strip()
            try:
                if target.lstrip("-").isdigit():
                    entity = await user_client.get_entity(int(target))
                else:
                    entity = await user_client.get_entity(target)
                info = format_user_info(entity)
                await event.edit(info)
            except Exception as e:
                await event.edit(f"❌ پیدا نشد: {str(e)[:80]}")
            return

        # ═══════════════════════════════════════
        # سیستم تپچی
        # ═══════════════════════════════════════
        elif text == "تپچی روشن":
            result = banner.enable()
            await event.edit(result)
            return

        elif text == "تپچی خاموش":
            result = banner.disable()
            await event.edit(result)
            return

        elif text == "حالت بنر فور":
            result = banner.set_mode("forward")
            await event.edit(result)
            return

        elif text == "حالت بنر کپی":
            result = banner.set_mode("copy")
            await event.edit(result)
            return

        elif text.startswith("بنر ") and event.is_reply and is_command(text):
            parts = text.split()
            if len(parts) < 2:
                await event.edit(
                    "❌ **فرمت اشتباه**\n"
                    "`بنر [ثانیه]` + ریپلای\nمثال: `بنر 300`"
                )
                return
            try:
                interval = int(parts[1])
                if interval < 10:
                    await event.edit("❌ حداقل فاصله 10 ثانیه")
                    return
            except ValueError:
                await event.edit("❌ ثانیه باید عدد باشد")
                return

            reply = await event.get_reply_message()
            chat_id = event.chat_id
            try:
                entity = await user_client.get_entity(chat_id)
                chat_name = extract_name(entity)
            except:
                chat_name = str(chat_id)

            result = banner.add_banner(
                chat_id=chat_id,
                chat_name=chat_name,
                from_chat_id=chat_id,
                message_id=reply.id,
                interval=interval
            )
            await event.edit(result)
            return

        elif (text.startswith("پاک کردن بنر ")
              or text.startswith("حذف بنر ")) and is_command(text):
            parts = text.split()
            if len(parts) < 3:
                await event.edit("❌ فرمت اشتباه\n`پاک کردن بنر [شماره]`")
                return
            try:
                banner_id = int(parts[-1])
            except ValueError:
                await event.edit("❌ شماره باید عدد باشد")
                return
            result = banner.remove_banner(event.chat_id, banner_id)
            await event.edit(result)
            return

        elif text == "لیست بنر":
            result = banner.get_chat_list(event.chat_id)
            await event.edit(result)
            return

        elif text in ("لیست کل بنر", "لیست کامل بنر"):
            result = banner.get_full_list()
            await event.edit(result)
            return

        elif text == "پاکسازی لیست بنر":
            result = banner.clear_chat_banners(event.chat_id)
            await event.edit(result)
            return

        elif text == "پاکسازی کل تپچی":
            result = banner.clear_all_banners()
            await event.edit(result)
            return

        # ═══════════════════════════════════════
        # دستورات افکت
        # ═══════════════════════════════════════
        elif text == "لیست افکت":
            await event.edit(effects.get_list_text())
            return

        elif text == "پاکسازی افکت":
            result = effects.clear_all()
            await event.edit(result)
            return

        elif text.startswith("افکت ") and is_command(text):
            rest = text[5:].strip()
            if rest.endswith(" روشن"):
                effect_name = rest[:-5].strip()
                result = effects.set_effect(effect_name, True)
                await event.edit(result)
                return
            elif rest.endswith(" خاموش"):
                effect_name = rest[:-6].strip()
                result = effects.set_effect(effect_name, False)
                await event.edit(result)
                return

        # ═══════════════════════════════════════
        # سیستم اسپم
        # ═══════════════════════════════════════
        elif (text.startswith("اسپم توقف ")
              or text.startswith("توقف اسپم ")) and is_command(text):
            rest = text.replace(
                "اسپم توقف", ""
            ).replace("توقف اسپم", "").strip()

            if rest == "همه":
                total = spam.stop_all()
                if total > 0:
                    await event.edit(f"🛑 **کل {total} اسپم متوقف شد**")
                else:
                    await event.edit("📭 **هیچ اسپم فعالی نبود**")
                return

            try:
                spam_id = int(rest)
                stopped = await spam.stop_spam(event.chat_id, spam_id)
                if stopped:
                    await event.edit(
                        f"🛑 **اسپم شماره `{spam_id}` متوقف شد**"
                    )
                else:
                    await event.edit(
                        f"❌ **اسپم شماره `{spam_id}` پیدا نشد**"
                    )
            except ValueError:
                await event.edit(
                    "❌ **فرمت اشتباه**\n"
                    "`اسپم توقف [شماره]`\n"
                    "`اسپم توقف همه`"
                )
            return

        elif text in ("اسپم توقف", "توقف اسپم", "اسپم خاموش"):
            stopped = await spam.stop_spam(event.chat_id)
            if stopped > 0:
                await event.edit(
                    f"🛑 **{stopped} اسپم در این چت متوقف شد**"
                )
            else:
                await event.edit("📭 **در این چت اسپمی فعال نیست**")
            return

        elif text in ("پاکسازی اسپم", "اسپم پاکسازی"):
            total = spam.stop_all()
            if total > 0:
                await event.edit(f"🛑 **کل {total} اسپم متوقف شد**")
            else:
                await event.edit("📭 **هیچ اسپم فعالی نبود**")
            return

        elif text in ("لیست اسپم", "اسپم لیست"):
            await event.edit(spam.get_chat_status_text(event.chat_id))
            return

        elif text in ("لیست کل اسپم", "لیست اسپم ها", "اسپم های فعال"):
            await event.edit(spam.get_full_status_text())
            return

        elif text.startswith("اسپم ") and is_command(text):
            rest = text[5:].strip()

            delete_mode = False
            if rest.startswith("حذفی "):
                delete_mode = True
                rest = rest[5:].strip()

            result = await _parse_and_start_spam(
                spam, event, rest, delete_mode, user_client
            )
            if result:
                await event.edit(result)
            return

        # ═══════════════════════════════════════
        # لیست و پاکسازی ریکت
        # ═══════════════════════════════════════
        elif text == "لیست ریکت":
            await event.edit(react.get_full_list())
            return

        elif text == "پاکسازی ریکت":
            result = react.clear_all()
            await event.edit(result)
            return

        # ═══════════════════════════════════════
        # ریکت متن خاص
        # ═══════════════════════════════════════
        elif text.startswith("ریکت متن ") and is_command(text):
            parts = text.split(maxsplit=3)
            # ریکت متن [ایموجی] [کلمه]
            if len(parts) >= 4:
                emoji = parts[2].strip()
                keyword = parts[3].strip()
                result = react.add_text_react(keyword, emoji)
                await event.edit(result)
            else:
                await event.edit(
                    "❌ **فرمت اشتباه**\n`ریکت متن [ایموجی] [کلمه]`\n"
                    "مثال: `ریکت متن ❤️ سلام`"
                )
            return

        elif text.startswith("حذف ریکت متن ") and is_command(text):
            keyword = text[14:].strip()
            if keyword:
                result = react.remove_text_react(keyword)
                await event.edit(result)
            else:
                await event.edit("❌ کلمه را وارد کنید")
            return

        # ═══════════════════════════════════════
        # حذف ریکت
        # ═══════════════════════════════════════
        elif text == "حذف ریکت" and event.is_reply:
            reply = await event.get_reply_message()
            sender_id = reply.sender_id
            chat_id = event.chat_id

            users = config.get("user_reactions", [])
            chats = config.get("chat_reactions", [])
            user_found = any(u["user_id"] == sender_id for u in users)
            chat_found = any(c["chat_id"] == chat_id for c in chats)

            if user_found:
                result = react.remove_by_id(sender_id)
                await event.edit(result)
            elif chat_found:
                result = react.remove_by_id(chat_id)
                await event.edit(result)
            else:
                await event.edit(
                    "❌ **این کاربر/چت در لیست ریکت نیست**\n\n"
                    "برای پاک ریکت از پیام: `پاک ریکت` + ریپلای"
                )
            return

        elif text == "پاک ریکت" and event.is_reply:
            reply = await event.get_reply_message()
            success, msg = await react.remove_reaction(
                event.chat_id, reply.id
            )
            try:
                await event.edit(msg)
            except:
                pass
            return

        elif text.startswith("حذف ریکت ") and is_command(text):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                await event.edit(
                    "❌ **فرمت اشتباه**\n"
                    "`حذف ریکت [شماره]`\n"
                    "`حذف ریکت [آیدی]`\n"
                    "`حذف ریکت [یوزرنیم]`\n"
                    "`حذف ریکت متن [کلمه]`"
                )
                return

            target = parts[2].strip()
            if target.lstrip("-").isdigit():
                num = int(target)
                total = (len(config.get("user_reactions", []))
                         + len(config.get("chat_reactions", []))
                         + len(config.get("text_reactions", [])))
                if 1 <= num <= total and num < 1000:
                    result = react.remove_by_index(num)
                else:
                    result = react.remove_by_id(num)
                await event.edit(result)
                return
            else:
                try:
                    entity = await user_client.get_entity(target)
                    result = react.remove_by_id(entity.id)
                    await event.edit(result)
                except Exception as e:
                    await event.edit(f"❌ پیدا نشد: {str(e)[:80]}")
                return

        # ═══════════════════════════════════════
        # افزودن ریکت
        # ═══════════════════════════════════════
        elif (text.startswith("ریکت اینجا ")
              or text.startswith("ریکت چت ")) and is_command(text):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                await event.edit(
                    "❌ **فرمت اشتباه**\n`ریکت اینجا [ایموجی]`"
                )
                return
            emoji = parts[2].strip()
            chat_id = event.chat_id
            try:
                entity = await user_client.get_entity(chat_id)
                chat_name = extract_name(entity)
            except:
                chat_name = str(chat_id)
            result = react.add_chat_react(chat_id, emoji, chat_name)
            await event.edit(result)
            return

        elif (text.startswith("ریکت ")
              and event.is_reply and is_command(text)):
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                await event.edit("❌ ایموجی وارد کنید\nمثال: `ریکت ❤️`")
                return

            emoji = parts[1].strip()
            reply = await event.get_reply_message()

            chat_keywords = ["چت", "اینجا", "گروه", "کانال", "here"]
            if (len(parts) >= 3
                    and parts[2].strip().lower() in chat_keywords):
                chat_id = event.chat_id
                try:
                    entity = await user_client.get_entity(chat_id)
                    chat_name = extract_name(entity)
                except:
                    chat_name = str(chat_id)
                result = react.add_chat_react(chat_id, emoji, chat_name)
                await event.edit(result)
                return

            user_id = reply.sender_id
            if not user_id:
                await event.edit("❌ فرستنده پیدا نشد")
                return
            try:
                entity = await user_client.get_entity(user_id)
                user_name = extract_name(entity)
            except:
                user_name = str(user_id)
            result = react.add_user_react(user_id, emoji, user_name)
            await event.edit(result)
            return

        elif (text.startswith("ریکت ")
              and not event.is_reply and is_command(text)):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                await event.edit(
                    "❌ **فرمت اشتباه**\n\n"
                    "**کاربر (ریپلای):** `ریکت [ایموجی]`\n"
                    "**چت فعلی:** `ریکت اینجا [ایموجی]`\n"
                    "**متن خاص:** `ریکت متن [ایموجی] [کلمه]`\n"
                    "**یوزرنیم:** `ریکت [ایموجی] [یوزرنیم]`\n"
                    "**آیدی:** `ریکت [ایموجی] [آیدی]`"
                )
                return

            emoji = parts[1].strip()
            target = parts[2].strip()

            try:
                if target.lstrip("-").isdigit():
                    target_id = int(target)
                    try:
                        entity = await user_client.get_entity(target_id)
                        name = extract_name(entity)
                    except:
                        entity = None
                        name = str(target_id)
                else:
                    entity = await user_client.get_entity(target)
                    target_id = entity.id
                    name = extract_name(entity)

                if entity and is_user_entity(entity):
                    result = react.add_user_react(target_id, emoji, name)
                else:
                    result = react.add_chat_react(target_id, emoji, name)
                await event.edit(result)
            except Exception as e:
                await event.edit(f"❌ خطا: {str(e)[:80]}")
            return

    # ═══════════════════════════════════════
    # هندلر اعمال افکت
    # ═══════════════════════════════════════
    @user_client.on(events.NewMessage(outgoing=True))
    async def effects_handler(event):
        text = event.raw_text.strip() if event.raw_text else ""
        if not text:
            return

        active_effects = config.get("active_effects", [])
        if not active_effects:
            return

        if is_command(text):
            return

        system_start = (
            "✅ **", "🔴 **", "❌ **", "🟢 **", "⚠️ **",
            "📭 **", "📋 **", "🗑 **", "🕐 **", "⏰ **",
            "📢 **", "🎨 **", "🔤 **", "👤 **", "💬 **",
            "❤️ **", "📤 **", "📝 **", "🛡 **", "🔧 **",
            "🆔 **", "🎯 **", "🚀 **", "🤖 **", "📊 **",
            "🔹 **", "🛑 **", "⚡ **", "📖 **",
        )
        if text.startswith(system_start):
            return

        if event.message.edit_date:
            return

        try:
            chat = await event.get_chat()
            if getattr(chat, 'bot', False):
                return
        except:
            pass

        try:
            await effects.apply_effects(event)
        except Exception as e:
            print(f"⚠️ خطا در افکت: {str(e)[:100]}")

    print("\n" + "=" * 50)
    print("🚀 سلف‌بات آماده به کار است!")
    print(f"📝 برای پنل: 'پنل' بنویسید")
    print(f"📖 برای راهنما: 'راهنما' بنویسید")
    print(f"🤖 Bot: @{bot_username}")
    print("=" * 50 + "\n")

    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )


if __name__ == "__main__":
    asyncio.run(main())