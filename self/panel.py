"""
ماژول پنل - ساخت دکمه‌ها و متن‌های پنل
نسخه بروزرسانی شده با دکمه‌های فشرده‌تر + اکشن + راهنما
"""

from telethon import Button
from fonts import get_font_list


BOT_USERNAME = ""


def set_bot_username(username):
    global BOT_USERNAME
    BOT_USERNAME = username


# ═══════════════════════════════════════
# پنل اصلی
# ═══════════════════════════════════════

def get_main_panel_text():
    return (
        "🛡 **پنل مدیریت پیشرفته**\n\n"
        "بخش مورد نظر را انتخاب کنید:"
    )


def get_main_panel_buttons():
    return [
        [
            Button.inline("⏰ ساعت", data="panel_clock"),
            Button.inline("❤️ ریکت", data="panel_react"),
        ],
        [
            Button.inline("📢 تپچی", data="panel_tapchi"),
            Button.inline("🎨 افکت", data="panel_effects"),
        ],
        [
            Button.inline("🚀 اسپم", data="panel_spam"),
            Button.inline("⚡ اکشن", data="panel_action"),
        ],
        [
            Button.inline("🔤 فونت", data="panel_font"),
            Button.inline("📖 راهنما", data="panel_help"),
        ],
        [Button.inline("❌ بستن پنل", data="panel_close")],
    ]


# ═══════════════════════════════════════
# پنل ساعت
# ═══════════════════════════════════════

def get_clock_panel_text(config):
    clock_status = "🟢 روشن" if config.get("clock_enabled") else "🔴 خاموش"
    bio_status = "🟢 روشن" if config.get("clock_bio_enabled") else "🔴 خاموش"
    bio_text = config.get("bio_text", "") or "تنظیم نشده"
    font_id = config.get("clock_font", 9)

    return (
        "⏰ **مدیریت ساعت**\n\n"
        f"  ▸ ساعت: {clock_status}\n"
        f"  ▸ بیو: {bio_status}\n"
        f"  ▸ متن بیو: `{bio_text}`\n"
        f"  ▸ فونت: `{font_id}`\n\n"
        "**دستورات:**\n"
        "`ساعت روشن/خاموش` | `ساعت بیو روشن/خاموش`\n"
        "`بیو [متن]` | `فونت ساعت [شماره]`"
    )


def get_clock_panel_buttons(config):
    clock_on = config.get("clock_enabled")
    bio_on = config.get("clock_bio_enabled")

    return [
        [
            Button.inline(
                "🔴 ساعت" if clock_on else "🟢 ساعت",
                data="clock_toggle"
            ),
            Button.inline(
                "🔴 بیو" if bio_on else "🟢 بیو",
                data="bio_toggle"
            ),
        ],
        [Button.inline("🔙 بازگشت", data="panel_main")],
    ]


# ═══════════════════════════════════════
# پنل ریکت
# ═══════════════════════════════════════

def get_react_panel_text(config):
    users = config.get("user_reactions", [])
    chats = config.get("chat_reactions", [])
    texts = config.get("text_reactions", [])

    text = "❤️ **ریکت خودکار**\n\n"
    text += f"  ▸ کاربران: `{len(users)}`\n"
    text += f"  ▸ چت‌ها/کانال‌ها: `{len(chats)}`\n"
    text += f"  ▸ متن‌های خاص: `{len(texts)}`\n\n"
    text += (
        "**📌 دستورات:**\n\n"
        "**➕ کاربر:** `ریکت [ایموجی]` + ریپلای\n"
        "**➕ چت:** `ریکت اینجا [ایموجی]`\n"
        "**➕ متن:** `ریکت متن [ایموجی] [کلمه]`\n"
        "**➕ کانال:** `ریکت [ایموجی] @channel`\n\n"
        "**🗑 حذف:**\n"
        "`حذف ریکت` + ریپلای\n"
        "`حذف ریکت [شماره/آیدی]`\n"
        "`حذف ریکت متن [کلمه]`\n\n"
        "**📋:** `لیست ریکت` | `پاکسازی ریکت`"
    )
    return text


def get_react_panel_buttons():
    return [
        [
            Button.inline("📋 لیست", data="react_list"),
            Button.inline("🧹 پاکسازی", data="react_clear"),
        ],
        [Button.inline("🔙 بازگشت", data="panel_main")],
    ]


# ═══════════════════════════════════════
# پنل تپچی
# ═══════════════════════════════════════

def get_tapchi_panel_text(config, banner_mgr):
    status = "🟢 روشن" if config.get("tapchi_enabled") else "🔴 خاموش"
    mode = config.get("banner_mode", "forward")
    mode_fa = "فوروارد" if mode == "forward" else "کپی"

    banners = config.get("banners", {})
    total_chats = len(banners)
    total_banners = sum(len(data["list"]) for data in banners.values())

    text = "📢 **تپچی (تبلیغات خودکار)**\n\n"
    text += f"  ▸ وضعیت: {status}\n"
    text += f"  ▸ حالت: `{mode_fa}`\n"
    text += f"  ▸ چت‌ها: `{total_chats}` | بنرها: `{total_banners}`\n\n"
    text += (
        "**دستورات:**\n"
        "`تپچی روشن/خاموش`\n"
        "`حالت بنر فور/کپی`\n"
        "`بنر [ثانیه]` + ریپلای\n"
        "`پاک کردن بنر [شماره]`\n"
        "`لیست بنر` | `لیست کل بنر`\n"
        "`پاکسازی لیست بنر` | `پاکسازی کل تپچی`"
    )
    return text


def get_tapchi_panel_buttons(config):
    enabled = config.get("tapchi_enabled", False)
    mode = config.get("banner_mode", "forward")

    return [
        [Button.inline(
            "🔴 خاموش" if enabled else "🟢 روشن",
            data="tapchi_toggle"
        )],
        [
            Button.inline(
                "📤 فوروارد ✅" if mode == "forward" else "📤 فوروارد",
                data="tapchi_mode_forward"
            ),
            Button.inline(
                "📋 کپی ✅" if mode == "copy" else "📋 کپی",
                data="tapchi_mode_copy"
            ),
        ],
        [
            Button.inline("📋 لیست", data="tapchi_list"),
            Button.inline("🧹 پاکسازی", data="tapchi_clear"),
        ],
        [Button.inline("🔙 بازگشت", data="panel_main")],
    ]


# ═══════════════════════════════════════
# پنل افکت
# ═══════════════════════════════════════

def get_effects_panel_text(config):
    from effects import AVAILABLE_EFFECTS
    active = config.get("active_effects", [])

    text = "🎨 **افکت‌های متنی**\n\n"
    text += f"  ▸ فعال: `{len(active)}`\n\n"

    for name_fa, key in AVAILABLE_EFFECTS.items():
        status = "🟢" if key in active else "⚪"
        text += f"  {status} {name_fa}\n"

    text += (
        "\n**دستورات:**\n"
        "`افکت [نام] روشن/خاموش`\n"
        "`لیست افکت` | `پاکسازی افکت`\n"
        "مثال: `افکت بولد روشن`"
    )
    return text


def get_effects_panel_buttons(config):
    from effects import AVAILABLE_EFFECTS
    active = config.get("active_effects", [])

    rows = []
    row = []
    for name_fa, key in AVAILABLE_EFFECTS.items():
        emoji = "🟢" if key in active else "⚪"
        row.append(Button.inline(f"{emoji}{name_fa}", data=f"eff_{key}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([Button.inline("🗑 پاکسازی", data="eff_clear")])
    rows.append([Button.inline("🔙 بازگشت", data="panel_main")])
    return rows


# ═══════════════════════════════════════
# پنل اسپم
# ═══════════════════════════════════════

def get_spam_panel_text(spam_mgr):
    all_chats = spam_mgr.get_all_chats_with_spam()
    total_spams = sum(len(spams) for spams in all_chats.values())
    text_spams = spam_mgr.get_text_spams_list()

    text = "🚀 **مدیریت اسپم**\n\n"
    text += f"  ▸ چت‌ها: `{len(all_chats)}`\n"
    text += f"  ▸ اسپم‌ها: `{total_spams}`\n"
    if text_spams:
        text += f"  ▸ اسپم متنی: `{len(text_spams)}`\n"
    text += (
        "\n**دستورات:**\n\n"
        "**شروع:**\n"
        "`اسپم [تاخیر] [متن]`\n"
        "`اسپم [تاخیر] [متن] [تعداد]`\n"
        "`اسپم [تاخیر] [متن] @target`\n"
        "`اسپم [تاخیر] [متن] [تعداد] @target`\n"
        "`اسپم حذفی [تاخیر] [متن]`\n"
        "ریپلای + `اسپم [تاخیر] [متن]` → ریپلای اسپم\n\n"
        "**اسپم متنی (تریگر):**\n"
        "`اسپم [تاخیر] [متن] متن‌خاص:[کلمه]`\n\n"
        "**توقف:**\n"
        "`اسپم توقف [شماره]` | `اسپم توقف`\n"
        "`اسپم توقف همه`\n\n"
        "**لیست:**\n"
        "`لیست اسپم` | `لیست کل اسپم`\n\n"
        "⚠️ حداقل تاخیر: 2.3 ثانیه"
    )
    return text


def get_spam_panel_buttons():
    return [
        [
            Button.inline("📋 لیست", data="spam_list"),
            Button.inline("🛑 توقف همه", data="spam_stop_all"),
        ],
        [Button.inline("🔙 بازگشت", data="panel_main")],
    ]


# ═══════════════════════════════════════
# پنل اکشن (جایگزین قبلی)
# ═══════════════════════════════════════

def get_action_panel_text(config):
    from action import ACTION_DESC
    actions = config.get("actions_list", [])
    enabled_count = sum(1 for a in actions if a.get("enabled", True))

    text = "⚡ **مدیریت اکشن**\n\n"
    text += f"  ▸ کل: `{len(actions)}` | فعال: `{enabled_count}`\n\n"

    if actions:
        text += "**اکشن‌های ثبت شده:**\n"
        for i, a in enumerate(actions, 1):
            status = "🟢" if a.get("enabled", True) else "🔴"
            name = a.get("chat_name") or str(a["chat_id"])
            atype = a.get("action_type", "تایپ")
            desc = ACTION_DESC.get(atype, "")
            text += f"  {status} `{i}` **{name}** → {atype}\n"
        text += "\n"

    text += "**انواع اکشن:**\n"
    for name, desc in ACTION_DESC.items():
        text += f"  ▹ `{name}` → _{desc}_\n"

    text += (
        "\n**دستورات (در چت مورد نظر):**\n"
        "`اکشن [نوع]` → فعال‌سازی\n"
        "`اکشن روشن/خاموش` → این چت\n"
        "`حذف اکشن` | `حذف اکشن [شماره]`\n"
        "`لیست اکشن` | `پاکسازی اکشن`\n\n"
        "مثال: `اکشن تایپ` یا `اکشن ویس`"
    )
    return text


def get_action_panel_buttons(config):
    actions = config.get("actions_list", [])

    rows = []

    if actions:
        row = []
        for i, a in enumerate(actions, 1):
            status = "🟢" if a.get("enabled", True) else "🔴"
            name = a.get("chat_name") or str(a["chat_id"])
            # کوتاه کن اسم
            short_name = name[:12] + ".." if len(name) > 14 else name
            row.append(
                Button.inline(
                    f"{status}{short_name}",
                    data=f"act_toggle_{a['chat_id']}"
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

    rows.append([
        Button.inline("📋 لیست", data="action_list"),
        Button.inline("🧹 پاکسازی", data="action_clear"),
    ])
    rows.append([Button.inline("🔙 بازگشت", data="panel_main")])
    return rows


# ═══════════════════════════════════════
# پنل فونت
# ═══════════════════════════════════════

def get_font_panel_text():
    return (
        "🔤 **انتخاب فونت ساعت**\n\n"
        + get_font_list() +
        "\n**دستور:** `فونت ساعت [شماره]`"
    )


def get_font_panel_buttons():
    rows = []
    row = []
    for i in range(1, 13):
        row.append(Button.inline(f"{i}", data=f"font_{i}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Button.inline("🔙 بازگشت", data="panel_main")])
    return rows


# ═══════════════════════════════════════
# پنل راهنما
# ═══════════════════════════════════════

def get_help_panel_text():
    return (
        "📖 **راهنمای کامل سلف‌بات**\n\n"

        "**⏰ ساعت:**\n"
        "ساعت فنسی در Last Name و بیو\n"
        "`ساعت روشن/خاموش` | `بیو [متن]`\n"
        "`فونت ساعت [1-12]` | `ساعت بیو روشن/خاموش`\n\n"

        "**❤️ ریکت خودکار:**\n"
        "ریکت خودکار روی کاربر، چت، کانال یا متن خاص\n"
        "`ریکت [ایموجی]` + ریپلای\n"
        "`ریکت اینجا [ایموجی]`\n"
        "`ریکت متن [ایموجی] [کلمه]`\n"
        "`حذف ریکت` | `لیست ریکت` | `پاکسازی ریکت`\n\n"

        "**📢 تپچی:**\n"
        "ارسال خودکار بنر در گروه‌ها\n"
        "`تپچی روشن/خاموش` | `بنر [ثانیه]` + ریپلای\n"
        "`حالت بنر فور/کپی` | `لیست بنر`\n\n"

        "**🎨 افکت متن:**\n"
        "تغییر فونت و استایل پیام‌ها\n"
        "`افکت [نام] روشن/خاموش`\n"
        "انواع: بولد، کج، بولد کج، زیرخط، خط خورده،\n"
        "وارونه، تدریجی، منشن، اسپویلر، کد،\n"
        "نقل قول، اسکریپت، دوخط، معکوس، فاصله\n\n"

        "**🚀 اسپم:**\n"
        "ارسال خودکار پیام با تاخیر\n"
        "`اسپم [تاخیر] [متن]`\n"
        "`اسپم [تاخیر] [متن] @target`\n"
        "`اسپم حذفی [تاخیر] [متن]`\n"
        "ریپلای + اسپم → ریپلای اسپم\n"
        "`اسپم توقف` | `لیست اسپم`\n\n"

        "**⚡ اکشن:**\n"
        "نمایش وضعیت (تایپ، ویس و ...) در چت\n"
        "`اکشن روشن/خاموش`\n"
        "`حالت اکشن [تایپ/ویس/استیکر/...]`\n\n"

        "**🆔 آیدی:**\n"
        "`آیدی` + ریپلای | `آیدی @user`\n\n"

        "**📋 پنل:**\n"
        "`پنل` → باز کردن | `بستن پنل` → بستن\n"
        "`بستن پنل ها` → بستن همه"
    )


def get_help_panel_buttons():
    return [
        [
            Button.inline("⏰ ساعت", data="help_clock"),
            Button.inline("❤️ ریکت", data="help_react"),
        ],
        [
            Button.inline("📢 تپچی", data="help_tapchi"),
            Button.inline("🎨 افکت", data="help_effects"),
        ],
        [
            Button.inline("🚀 اسپم", data="help_spam"),
            Button.inline("⚡ اکشن", data="help_action"),
        ],
        [Button.inline("🔙 بازگشت", data="panel_main")],
    ]


# ═══════════════════════════════════════
# راهنمای تفصیلی هر بخش
# ═══════════════════════════════════════

HELP_TEXTS = {
    "help_clock": (
        "⏰ **راهنمای ساعت**\n\n"
        "ساعت فنسی را در Last Name و بیو نمایش می‌دهد.\n\n"
        "**دستورات:**\n"
        "`ساعت روشن` → فعال‌سازی ساعت\n"
        "`ساعت خاموش` → غیرفعال‌سازی\n"
        "`بیو [متن]` → تنظیم متن بیو\n"
        "`ساعت بیو روشن` → نمایش ساعت در بیو\n"
        "`فونت ساعت [1-12]` → تغییر فونت\n\n"
        "**نکته:** ساعت هر دقیقه بروزرسانی می‌شود."
    ),
    "help_react": (
        "❤️ **راهنمای ریکت خودکار**\n\n"
        "**روی کاربر:**\n"
        "`ریکت [ایموجی]` + ریپلای\n"
        "`ریکت [ایموجی] @username`\n"
        "`ریکت [ایموجی] [آیدی]`\n\n"
        "**روی چت/کانال:**\n"
        "`ریکت اینجا [ایموجی]`\n"
        "`ریکت چت [ایموجی]`\n\n"
        "**روی متن خاص:**\n"
        "`ریکت متن [ایموجی] [کلمه]`\n"
        "وقتی کسی دقیقاً آن کلمه را بنویسد ریکت می‌زند\n\n"
        "**حذف:**\n"
        "`حذف ریکت` + ریپلای\n"
        "`حذف ریکت [شماره]`\n"
        "`حذف ریکت متن [کلمه]`\n\n"
        "**نکته:** ریکت روی کانال هم کار می‌کند.\n"
        "آیدی عددی یا یوزرنیم کانال را بدهید."
    ),
    "help_tapchi": (
        "📢 **راهنمای تپچی**\n\n"
        "ارسال خودکار بنر (تبلیغ) در گروه‌ها\n\n"
        "**تنظیم بنر:**\n"
        "1. در گروه موردنظر روی پیام ریپلای بزنید\n"
        "2. `بنر [ثانیه]` بنویسید\n\n"
        "**حالت‌ها:**\n"
        "`حالت بنر فور` → فوروارد پیام\n"
        "`حالت بنر کپی` → کپی محتوا\n\n"
        "**مدیریت:**\n"
        "`تپچی روشن/خاموش`\n"
        "`لیست بنر` | `لیست کل بنر`\n"
        "`پاک کردن بنر [شماره]`\n"
        "`پاکسازی لیست بنر` | `پاکسازی کل تپچی`"
    ),
    "help_effects": (
        "🎨 **راهنمای افکت متن**\n\n"
        "هر پیامی بنویسید با افکت ارسال می‌شود.\n\n"
        "**انواع افکت:**\n"
        "▸ بولد، کج، بولد کج\n"
        "▸ زیرخط، خط خورده\n"
        "▸ وارونه، تدریجی\n"
        "▸ منشن، اسپویلر\n"
        "▸ کد (مونواسپیس)\n"
        "▸ نقل قول، اسکریپت\n"
        "▸ دوخط، معکوس، فاصله\n\n"
        "**دستورات:**\n"
        "`افکت [نام] روشن`\n"
        "`افکت [نام] خاموش`\n"
        "`لیست افکت` | `پاکسازی افکت`"
    ),
    "help_spam": (
        "🚀 **راهنمای اسپم**\n\n"
        "**اسپم عادی:**\n"
        "`اسپم [تاخیر] [متن]`\n"
        "`اسپم [تاخیر] [متن] [تعداد]`\n\n"
        "**اسپم حذفی:**\n"
        "`اسپم حذفی [تاخیر] [متن]`\n\n"
        "**اسپم با تارگت:**\n"
        "`اسپم [تاخیر] [متن] @username`\n"
        "`اسپم [تاخیر] [متن] [تعداد] @target`\n"
        "ریپلای + اسپم → اسپم ریپلای\n\n"
        "**اسپم متنی (تریگر):**\n"
        "`اسپم [تاخیر] [متن] متن‌خاص:[کلمه]`\n"
        "وقتی کسی آن کلمه را بنویسد پاسخ می‌دهد\n\n"
        "**توقف:**\n"
        "`اسپم توقف [شماره]`\n"
        "`اسپم توقف` → همه اسپم‌های چت\n"
        "`اسپم توقف همه`\n\n"
        "⚠️ حداقل تاخیر: 2.3 ثانیه"
    ),
    "help_action": (
        "⚡ **راهنمای اکشن**\n\n"
        "نمایش وضعیت (مثلاً در حال تایپ) در چت\n\n"
        "**دستورات:**\n"
        "`اکشن روشن` → فعال‌سازی\n"
        "`اکشن خاموش` → غیرفعال‌سازی\n"
        "`حالت اکشن [نوع]` → تغییر نوع\n\n"
        "**انواع:**\n"
        "`تایپ` → در حال تایپ\n"
        "`ویس` → در حال ضبط صدا\n"
        "`استیکر` → در حال انتخاب استیکر\n"
        "`مخاطب` → در حال انتخاب مخاطب\n"
        "`ویدیو گرد` → در حال ضبط ویدیو گرد\n"
        "`آپلود ویدیو` → در حال آپلود ویدیو\n"
        "`آپلود عکس` → در حال آپلود عکس\n"
        "`آپلود فایل` → در حال آپلود فایل\n"
        "`بازی` → در حال بازی\n\n"
        "**مثال:** `حالت اکشن ویس`"
    ),
}