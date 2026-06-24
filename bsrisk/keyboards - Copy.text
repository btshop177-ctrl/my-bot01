from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)


# ═══════════════ ادمین ═══════════════

def admin_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 آمار ربات"), KeyboardButton(text="📢 مدیریت کانال‌ها")],
            [KeyboardButton(text="👥 لیست کاربران"), KeyboardButton(text="📨 ارسال همگانی")],
            [KeyboardButton(text="🔧 مدیریت کاربر")],
        ],
        resize_keyboard=True
    )


def channel_management_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ افزودن کانال"), KeyboardButton(text="➖ حذف کانال")],
            [KeyboardButton(text="📋 لیست کانال‌ها")],
            [KeyboardButton(text="🔙 بازگشت به پنل ادمین")],
        ],
        resize_keyboard=True
    )


def user_management_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ ویرایش نام کاربر"), KeyboardButton(text="💰 ویرایش سکه")],
            [KeyboardButton(text="🚫 بن کاربر"), KeyboardButton(text="✅ آنبن کاربر")],
            [KeyboardButton(text="🔙 بازگشت به پنل ادمین")],
        ],
        resize_keyboard=True
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ انصراف")]],
        resize_keyboard=True
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

    for i in range(start):
        if not users[i]['full_name'] and not users[i]['username']:
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


# ═══════════════ کاربر ═══════════════

def user_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="💰 موجودی")],
            [KeyboardButton(text="✏️ تغییر نام"), KeyboardButton(text="📋 راهنما")],
        ],
        resize_keyboard=True
    )


def join_channels_keyboard(channels: list) -> InlineKeyboardMarkup:
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