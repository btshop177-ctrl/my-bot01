"""
پنل اینلاین مشترک - همه کاربران از «ربات مدیریت» برای پنل سلف خود استفاده می‌کنند

نحوه کار بدون قاطی شدن درخواست‌ها:
- هر callback با فرمت  s:<account_id>:<payload>  است؛ یعنی پنل هر کاربر
  فقط با آیدی اکانت خودش کار می‌کند و کلیک بقیه رد می‌شود.
- متن پنل‌ها از config.json همان کاربر (fresh از دیسک) رندر می‌شود،
  پس اطلاعات کاربران همیشه جداست.
- تغییرات فلگ/لیست‌ها به‌صورت اتمیک روی config.json کاربر نوشته می‌شود
  و سلف کاربر با ConfigWatcher آن‌ها را اعمال می‌کند.
- اکشن‌های بدون فلگ (مثل توقف اسپم) به‌صورت دستور در commands.json
  کنار کانفیگ گذاشته می‌شوند و سلف همان کاربر اجرایشان می‌کند.
"""

import json
import os
import time

from telethon import Button

from panel import (
    get_main_panel_text,
    get_clock_panel_text,
    get_react_panel_text,
    get_tapchi_panel_text,
    get_effects_panel_text,
    get_spam_panel_text,
    get_font_panel_text,
    get_action_panel_text,
    get_pvlock_panel_text,
    get_help_panel_text,
    HELP_TEXTS,
)


class CfgShim:
    """شبیه‌سازی ConfigManager روی دیکشنری خام config.json کاربر"""

    def __init__(self, data):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)


# ═══════════════════════════════════════
# خواندن/نوشتن امن config کاربر
# ═══════════════════════════════════════

def load_user_config(config_abs_path):
    for attempt in range(3):
        try:
            with open(config_abs_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            time.sleep(0.05 * (attempt + 1))
    return {}


def save_user_config(config_abs_path, data):
    tmp = config_abs_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config_abs_path)


def append_panel_command(config_abs_path, command):
    """افزودن دستور برای پروسه سلف کاربر (commands.json کنار کانفیگ)"""
    cmd_file = os.path.join(
        os.path.dirname(config_abs_path) or ".", "commands.json"
    )
    commands = []
    if os.path.exists(cmd_file):
        try:
            with open(cmd_file, "r", encoding="utf-8") as f:
                commands = json.load(f)
        except (json.JSONDecodeError, OSError):
            commands = []
    commands.append({"cmd": command, "ts": time.time()})
    tmp = cmd_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(commands, f, ensure_ascii=False)
    os.replace(tmp, cmd_file)


# ═══════════════════════════════════════
# ساخت callback نام‌فضای دار
# ═══════════════════════════════════════

def cb(account_id, payload):
    return f"s:{account_id}:{payload}"


def B(text, account_id, payload):
    return Button.inline(text, data=cb(account_id, payload))


def BACK(text, account_id, payload):
    return [Button.inline(text, data=cb(account_id, payload))]


# ═══════════════════════════════════════
# رندر بخش‌های پنل
# ═══════════════════════════════════════

def render_shared_panel(account_id, section, cfg):
    """
    برمی‌گرداند: (text, buttons, parse_ok)
    section: main/clock/react/tapchi/effects/spam/action/pvlock/font/help/...
    """
    shim = CfgShim(cfg)
    A = account_id

    if section == "main":
        return get_main_panel_text(), [
            [B("⏰ ساعت", A, "clock"), B("❤️ ریکت", A, "react")],
            [B("📢 تپچی", A, "tapchi"), B("🎨 افکت", A, "effects")],
            [B("🚀 اسپم", A, "spam"), B("⚡ اکشن", A, "action")],
            [B("🔒 قفل پیوی", A, "pvlock"), B("🔤 فونت", A, "font")],
            [B("📖 راهنما", A, "help")],
            [B("❌ بستن پنل", A, "close")],
        ]

    if section == "clock":
        return get_clock_panel_text(shim), [
            [
                B("🔴 ساعت" if cfg.get("clock_enabled") else "🟢 ساعت",
                  A, "clk_tgl"),
                B("🔴 بیو" if cfg.get("clock_bio_enabled") else "🟢 بیو",
                  A, "bio_tgl"),
            ],
            BACK("🔙 بازگشت", A, "m"),
        ]

    if section == "react":
        return get_react_panel_text(shim), [
            [B("🧹 پاکسازی همه ریکت‌ها", A, "react_clear_ask")],
            BACK("🔙 بازگشت", A, "m"),
        ]

    if section == "react_clear_ask":
        return (
            "⚠️ **آیا مطمئنید؟**\nهمه ریکت‌ها حذف می‌شوند.\n"
            "(تا چند ثانیه دیگر در سلف اعمال می‌شود)"
        ), [
            BACK("✅ بله", A, "react_clear_ok"),
            BACK("🔙 انصراف", A, "react"),
        ]

    if section == "tapchi":
        enabled = cfg.get("tapchi_enabled", False)
        mode = cfg.get("banner_mode", "forward")
        return get_tapchi_panel_text(shim, None), [
            [B("🔴 خاموش" if enabled else "🟢 روشن", A, "tap_tgl")],
            [
                B("📤 فوروارد ✅" if mode == "forward" else "📤 فوروارد",
                  A, "tap_mode_f"),
                B("📋 کپی ✅" if mode == "copy" else "📋 کپی",
                  A, "tap_mode_c"),
            ],
            [B("🧹 پاکسازی همه بنرها", A, "tap_clear_ask")],
            BACK("🔙 بازگشت", A, "m"),
        ]

    if section == "tap_clear_ask":
        return (
            "⚠️ **آیا مطمئنید؟**\nهمه بنرها حذف می‌شوند."
        ), [
            BACK("✅ بله", A, "tap_clear_ok"),
            BACK("🔙 انصراف", A, "tapchi"),
        ]

    if section == "effects":
        from effects import AVAILABLE_EFFECTS
        active = cfg.get("active_effects", [])
        rows = []
        row = []
        for name_fa, key in AVAILABLE_EFFECTS.items():
            emoji = "🟢" if key in active else "⚪"
            row.append(B(f"{emoji}{name_fa}", A, f"eff_{key}"))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append(BACK("🗑 پاکسازی", A, "eff_clear"))
        rows.append(BACK("🔙 بازگشت", A, "m"))
        return get_effects_panel_text(shim), rows

    if section == "spam":
        text = (
            "🚀 **مدیریت اسپم**\n\n"
            "شروع و مدیریت اسپم‌ها با دستورات چت انجام می‌شود:\n"
            "`اسپم [تاخیر] [متن]` | `لیست اسپم`\n\n"
            "از اینجا فقط می‌توانید همه اسپم‌ها را متوقف کنید:"
        )
        return text, [
            [B("🛑 توقف همه اسپم‌ها", A, "spam_stop_ask")],
            BACK("🔙 بازگشت", A, "m"),
        ]

    if section == "spam_stop_ask":
        return (
            "⚠️ **آیا مطمئنید؟**\nهمه اسپم‌ها متوقف می‌شوند."
        ), [
            BACK("✅ بله", A, "spam_stop_ok"),
            BACK("🔙 انصراف", A, "spam"),
        ]

    if section == "action":
        from action import ACTION_DESC
        actions = cfg.get("actions_list", [])
        rows = []
        row = []
        for a in actions:
            status = "🟢" if a.get("enabled", True) else "🔴"
            name = a.get("chat_name") or str(a["chat_id"])
            short = name[:12] + ".." if len(name) > 14 else name
            row.append(B(f"{status}{short}", A, f"actT_{a['chat_id']}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        if actions:
            rows.append(BACK("🧹 پاکسازی همه", A, "act_clear_ok"))
        rows.append(BACK("🔙 بازگشت", A, "m"))
        return get_action_panel_text(shim), rows

    if section == "pvlock":
        locks = cfg.get("pv_locks", [])
        rows = []
        row = []
        for lock in locks:
            name = lock.get("user_name") or str(lock["user_id"])
            for ch in ('*', '_', '`', '[', ']', '~'):
                name = name.replace(ch, '')
            short = name[:14] + ".." if len(name) > 16 else name
            row.append(B(f"🔓{short}", A, f"pvu_{lock['user_id']}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        if locks:
            rows.append(BACK("🧹 پاکسازی همه", A, "pvl_clear_ok"))
        rows.append(BACK("🔙 بازگشت", A, "m"))
        return get_pvlock_panel_text(shim), rows

    if section == "font":
        rows = []
        row = []
        for i in range(1, 13):
            row.append(B(str(i), A, f"f_{i}"))
            if len(row) == 4:
                rows.append(row)
                row = []
        rows.append(BACK("🔙 بازگشت", A, "m"))
        return get_font_panel_text(), rows

    if section == "help":
        return get_help_panel_text(), [
            [B("⏰ ساعت", A, "h_clock"), B("❤️ ریکت", A, "h_react")],
            [B("📢 تپچی", A, "h_tapchi"), B("🎨 افکت", A, "h_effects")],
            [B("🚀 اسپم", A, "h_spam"), B("⚡ اکشن", A, "h_action")],
            [B("🔒 قفل پیوی", A, "h_pvlock")],
            BACK("🔙 بازگشت", A, "m"),
        ]

    if section.startswith("h_"):
        text = HELP_TEXTS.get("help_" + section[2:], "❌ یافت نشد")
        return text, [
            BACK("🔙 راهنما", A, "help"),
            BACK("🔙 منو", A, "m"),
        ]

    return None, None


# ═══════════════════════════════════════
# اعمال اکشن روی config کاربر
# برمی‌گرداند: (section_jadid, answer_ya_None)
# اگر None برگرداند یعنی payload شناخته نشد.
# ═══════════════════════════════════════

def apply_shared_action(payload, cfg):
    """
    payload بخش اکشن callback است (بدون s:uid:)
    cfg را درجا تغییر می‌دهد؛ (section, answer, needs_command)
    """

    # ─── ناوبری ساده ───
    simple_nav = {
        "m": "main", "clock": "clock", "react": "react",
        "tapchi": "tapchi", "effects": "effects", "spam": "spam",
        "action": "action", "pvlock": "pvlock", "font": "font",
        "help": "help",
        "react_clear_ask": "react_clear_ask",
        "tap_clear_ask": "tap_clear_ask",
        "spam_stop_ask": "spam_stop_ask",
    }
    if payload in simple_nav:
        return simple_nav[payload], None, None

    if payload.startswith("h_"):
        return payload, None, None  # صفحه راهنما

    if payload == "close":
        return "CLOSE", None, None

    # ─── ساعت ───
    if payload == "clk_tgl":
        cfg["clock_enabled"] = not cfg.get("clock_enabled", False)
        return "clock", (
            "✅ ساعت روشن شد" if cfg["clock_enabled"] else "🔴 ساعت خاموش شد"
        ), None

    if payload == "bio_tgl":
        if not cfg.get("bio_text"):
            return "clock", "❌ ابتدا با دستور «بیو [متن]» متن بیو را تنظیم کنید", None
        cfg["clock_bio_enabled"] = not cfg.get("clock_bio_enabled", False)
        return "clock", (
            "✅ ساعت بیو روشن شد" if cfg["clock_bio_enabled"]
            else "🔴 ساعت بیو خاموش شد"
        ), None

    # ─── ریکت ───
    if payload == "react_clear_ok":
        cfg["user_reactions"] = []
        cfg["chat_reactions"] = []
        cfg["text_reactions"] = []
        return "react", "🗑 همه ریکت‌ها پاک شدند", None

    # ─── تپچی ───
    if payload == "tap_tgl":
        cfg["tapchi_enabled"] = not cfg.get("tapchi_enabled", False)
        return "tapchi", (
            "✅ تپچی روشن شد" if cfg["tapchi_enabled"] else "🔴 تپچی خاموش شد"
        ), None

    if payload == "tap_mode_f":
        cfg["banner_mode"] = "forward"
        return "tapchi", "✅ حالت: فوروارد", None

    if payload == "tap_mode_c":
        cfg["banner_mode"] = "copy"
        return "tapchi", "✅ حالت: کپی", None

    if payload == "tap_clear_ok":
        cfg["banners"] = {}
        return "tapchi", "🗑 همه بنرها حذف شدند", None

    # ─── افکت ───
    if payload.startswith("eff_"):
        key = payload[4:]
        if key == "clear":
            cfg["active_effects"] = []
            return "effects", "🗑 همه افکت‌ها پاک شدند", None
        active = cfg.get("active_effects", [])
        if key in active:
            active.remove(key)
            msg = "🔴 افکت خاموش شد"
        else:
            active.append(key)
            msg = "🟢 افکت روشن شد"
        cfg["active_effects"] = active
        return "effects", msg, None

    # ─── اسپم ───
    if payload == "spam_stop_ok":
        return "spam", "🛑 همه اسپم‌ها متوقف شدند", "spam_stop_all"

    # ─── اکشن ───
    if payload.startswith("actT_"):
        try:
            chat_id = int(payload[5:])
        except ValueError:
            return "action", "❌", None
        for a in cfg.get("actions_list", []):
            if a["chat_id"] == chat_id:
                a["enabled"] = not a.get("enabled", True)
                return "action", (
                    "🟢 اکشن روشن شد" if a["enabled"] else "🔴 اکشن خاموش شد"
                ), None
        return "action", "❌ اکشن یافت نشد", None

    if payload == "act_clear_ok":
        cfg["actions_list"] = []
        return "action", "🗑 همه اکشن‌ها حذف شدند", None

    # ─── قفل پیوی ───
    if payload.startswith("pvu_"):
        try:
            user_id = int(payload[4:])
        except ValueError:
            return "pvlock", "❌", None
        locks = cfg.get("pv_locks", [])
        cfg["pv_locks"] = [l for l in locks if l["user_id"] != user_id]
        return "pvlock", "🔓 قفل پیوی حذف شد", None

    if payload == "pvl_clear_ok":
        cfg["pv_locks"] = []
        return "pvlock", "🗑 همه قفل‌های پیوی حذف شدند", None

    # ─── فونت ───
    if payload.startswith("f_"):
        try:
            font_id = int(payload[2:])
        except ValueError:
            return "font", "❌", None
        if 1 <= font_id <= 12:
            cfg["clock_font"] = font_id
            return "font", f"✅ فونت {font_id} انتخاب شد", None
        return "font", "❌ شماره فونت نامعتبر", None

    return None, None, None
