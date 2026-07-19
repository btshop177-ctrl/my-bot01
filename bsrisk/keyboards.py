from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)


# ═══════════════ منوی اصلی خصوصی ═══════════════
# این کیبورد فقط در گفت‌وگوی خصوصی استفاده می‌شود. در گروه و کانال
# هیچ ReplyKeyboardMarkup ساخته نمی‌شود.
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="فوتبال"), KeyboardButton(text="بازی ها")],
            [KeyboardButton(text="سلف"), KeyboardButton(text="مود")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_main_menu() -> ReplyKeyboardMarkup:
    """منوی اصلی ادمین؛ پنل هر بخش در هندلر همان بخش باز می‌شود."""
    return main_menu()


def user_main_menu() -> ReplyKeyboardMarkup:
    """منوی اصلی کاربر در PV."""
    return main_menu()


def user_games_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="💰 موجودی")],
            [KeyboardButton(text="✏️ تغییر نام"), KeyboardButton(text="📋 راهنما")],
            [KeyboardButton(text="🔙 منوی اصلی")],
        ],
        resize_keyboard=True,
    )


def admin_games_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 آمار ربات"), KeyboardButton(text="🔧 مدیریت کاربر")],
            [KeyboardButton(text="📢 مدیریت کانال‌ها")],
            [KeyboardButton(text="🔙 منوی اصلی")],
        ],
        resize_keyboard=True,
    )


def admin_section_placeholder_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 منوی اصلی")]],
        resize_keyboard=True,
    )


def channel_management_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ افزودن کانال"), KeyboardButton(text="➖ حذف کانال")],
            [KeyboardButton(text="📋 لیست کانال‌ها")],
            [KeyboardButton(text="🔙 بازگشت به پنل بازی‌ها")],
        ],
        resize_keyboard=True,
    )


def user_management_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ ویرایش نام کاربر"), KeyboardButton(text="💰 ویرایش سکه")],
            [KeyboardButton(text="🚫 بن کاربر"), KeyboardButton(text="✅ آنبن کاربر")],
            [KeyboardButton(text="🔙 بازگشت به پنل بازی‌ها")],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ انصراف")]],
        resize_keyboard=True,
    )


def channels_list_inline(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {ch['channel_title']}",
                callback_data=f"remove_ch:{ch['channel_id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══════════════ لیست کاربران برای انتخاب ═══════════════
def users_list_inline(users: list, action: str, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    buttons = []
    none_counter = 0
    start = page * per_page
    end = start + per_page

    for user in users[:start]:
        if not user['full_name'] and not user['username']:
            none_counter += 1

    for user in users[start:end]:
        uid = user['user_id']

        if user['full_name'] and user['full_name'].strip():
            display = user['full_name']
        elif user['username']:
            display = f"@{user['username']}"
        else:
            none_counter += 1
            display = f"None{none_counter}"

        status = " 🚫" if user['is_banned'] else ""

        if len(display) > 25:
            display = display[:22] + "..."

        buttons.append([
            InlineKeyboardButton(
                text=f"{display}{status} | {uid}",
                callback_data=f"sel_user:{action}:{uid}"
            )
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="◀️ قبلی",
            callback_data=f"users_page:{action}:{page - 1}"
        ))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton(
            text="بعدی ▶️",
            callback_data=f"users_page:{action}:{page + 1}"
        ))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_action")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══════════════ گروه: فقط InlineKeyboardMarkup ═══════════════
def group_admin_panel_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="⚙️ تنظیم جوین اجباری", callback_data="grp:join")],
        [InlineKeyboardButton(text="🚫 راهنمای بن کاربر", callback_data="grp:ban_help")],
        [InlineKeyboardButton(text="🔇 راهنمای سکوت", callback_data="grp:mute_help")],
    ]
    if is_owner:
        buttons.append([
            InlineKeyboardButton(text="👥 مدیریت دسترسی ادمین‌ها", callback_data="grp:permissions")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def group_join_settings_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 خاموش کردن جوین اجباری" if enabled else "🟢 روشن کردن جوین اجباری"
    toggle_action = "off" if enabled else "on"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"grp:join:{toggle_action}")],
        [InlineKeyboardButton(text="📋 کانال‌های این گروه", callback_data="grp:join:list")],
        [InlineKeyboardButton(text="➕ افزودن کانال با دستور", callback_data="grp:join:add_help")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="grp:back")],
    ])


def group_permissions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ اعطای دسترسی با دستور", callback_data="grp:perm:add_help")],
        [InlineKeyboardButton(text="➖ لغو دسترسی با دستور", callback_data="grp:perm:remove_help")],
        [InlineKeyboardButton(text="📋 مشاهده دسترسی‌ها", callback_data="grp:perm:list")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="grp:back")],
    ])


# ═══════════════ کاربر ═══════════════
def join_channels_keyboard(channels: list) -> InlineKeyboardMarkup:
    """کیبورد جوین اجباری؛ این کیبورد فقط در PV ارسال می‌شود."""
    buttons = []
    for ch in channels:
        link = ch['invite_link'] or f"https://t.me/{ch['channel_username']}"
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {ch['channel_title']}",
                url=link
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="✅ بررسی عضویت",
            callback_data="check_join"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
