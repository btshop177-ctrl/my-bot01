from telegram import (
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton,
)
from config import MIN_BET, MAX_BET


class Btn:
    MATCHES = "⚽ مسابقات"
    MY_PREDS = "📊 پیش‌بینی‌های من"
    ACCOUNT = "👤 حساب من"
    HELP = "📋 راهنما"
    EDIT_NAME = "✏️ ویرایش اسم"
    DEPOSIT = "💎 واریز"
    WITHDRAW = "📤 برداشت"
    BACK_MAIN = "🔙 منوی اصلی"
    ADD_MATCH = "➕ افزودن مسابقه"
    MANAGE_MATCHES = "✏️ مدیریت مسابقات"
    CHANNELS = "📢 کانال‌ها"
    USERS = "👥 کاربران"
    ADMINS = "👑 ادمین‌ها"
    STATS = "📊 آمار"
    BROADCAST = "📨 ارسال همگانی"
    TREASURY = "🏛️ خزانه"
    BACK_ADMIN = "🔙 پنل ادمین"
    ADD_CHANNEL = "➕ افزودن کانال"
    LIST_CHANNELS = "👀 نمایش کانال‌ها"
    DEL_CHANNEL = "❌ حذف کانال"
    LIST_USERS = "👀 لیست کاربران"
    SEARCH_USER = "🔍 جستجوی کاربر"
    BAN_TOGGLE = "🚫 بن/رفع بن"
    EDIT_USER_COINS = "💎 ویرایش سکه"
    ADD_ADMIN = "👑 افزودن ادمین"
    DEL_ADMIN = "🗑️ حذف ادمین"
    LIST_ADMINS = "👀 نمایش ادمین‌ها"
    TREASURY_VIEW = "💰 موجودی خزانه"
    TREASURY_WITHDRAW = "📤 برداشت خزانه"
    TREASURY_HISTORY = "📜 تاریخچه خزانه"
    IRAN_TIME = "🕐 ساعت ایران"

CANCEL_TEXTS = {Btn.BACK_MAIN, Btn.BACK_ADMIN, "/cancel"}
STATUS_EMOJI = {"upcoming": "🟡", "closed": "🟠", "finished": "🟢", "cancelled": "🔴"}


def user_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton(Btn.MATCHES)],
        [KeyboardButton(Btn.MY_PREDS)],
        [KeyboardButton(Btn.ACCOUNT)],
        [KeyboardButton(Btn.HELP)],
    ], resize_keyboard=True)

def account_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton(Btn.EDIT_NAME)],
        [KeyboardButton(Btn.DEPOSIT), KeyboardButton(Btn.WITHDRAW)],
        [KeyboardButton(Btn.BACK_MAIN)],
    ], resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton(Btn.ADD_MATCH), KeyboardButton(Btn.MANAGE_MATCHES)],
        [KeyboardButton(Btn.CHANNELS), KeyboardButton(Btn.USERS)],
        [KeyboardButton(Btn.ADMINS), KeyboardButton(Btn.TREASURY)],
        [KeyboardButton(Btn.STATS), KeyboardButton(Btn.BROADCAST)],
        [KeyboardButton(Btn.IRAN_TIME)],
    ], resize_keyboard=True)

def channel_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton(Btn.ADD_CHANNEL), KeyboardButton(Btn.LIST_CHANNELS)],
        [KeyboardButton(Btn.DEL_CHANNEL)],
        [KeyboardButton(Btn.BACK_ADMIN)],
    ], resize_keyboard=True)

def user_mgmt_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton(Btn.LIST_USERS)],
        [KeyboardButton(Btn.SEARCH_USER), KeyboardButton(Btn.BAN_TOGGLE)],
        [KeyboardButton(Btn.EDIT_USER_COINS)],
        [KeyboardButton(Btn.BACK_ADMIN)],
    ], resize_keyboard=True)

def admin_mgmt_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton(Btn.ADD_ADMIN), KeyboardButton(Btn.DEL_ADMIN)],
        [KeyboardButton(Btn.LIST_ADMINS)],
        [KeyboardButton(Btn.BACK_ADMIN)],
    ], resize_keyboard=True)

def treasury_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton(Btn.TREASURY_VIEW)],
        [KeyboardButton(Btn.TREASURY_WITHDRAW)],
        [KeyboardButton(Btn.TREASURY_HISTORY)],
        [KeyboardButton(Btn.BACK_ADMIN)],
    ], resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("/cancel")]], resize_keyboard=True)

def remove_keyboard():
    return ReplyKeyboardRemove()


# ═══ Inline ═══
def join_channels_keyboard(channels):
    buttons = []
    for ch in channels:
        ident = ch["channel_identifier"]
        title = ch["channel_title"] or ident
        url = f"https://t.me/{ident.lstrip('@')}" if ident.startswith("@") else f"https://t.me/c/{ident[4:]}" if ident.startswith("-100") else f"https://t.me/{ident}"
        buttons.append([InlineKeyboardButton(f"📢 {title}", url=url)])
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")])
    return InlineKeyboardMarkup(buttons)

def upcoming_matches_inline(matches):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚽ {m['caption'][:50]}", callback_data=f"match_{m['id']}")]
        for m in matches])

def prediction_inline(match, has_existing_bet=False):
    """اگه قبلاً شرط بسته، دکمه تغییر شرط نشون بده"""
    mid = match["id"]
    buttons = [
        [InlineKeyboardButton(f"🟠 {match['option_1']}", callback_data=f"pred_{mid}_option_1")],
        [InlineKeyboardButton(f"🤝 {match['option_2']}", callback_data=f"pred_{mid}_option_2")],
        [InlineKeyboardButton(f"🟡 {match['option_3']}", callback_data=f"pred_{mid}_option_3")],
    ]
    if has_existing_bet:
        buttons.append([InlineKeyboardButton("🔄 لغو شرط فعلی و شرط جدید",
                                             callback_data=f"cancelbet_{mid}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_matches")])
    return InlineKeyboardMarkup(buttons)

def bet_amount_inline(match_id, prediction):
    amounts = [a for a in [50, 100, 200, 500, 1000, 5000] if MIN_BET <= a <= MAX_BET]
    buttons, row = [], []
    for i, a in enumerate(amounts):
        row.append(InlineKeyboardButton(f"💰 {a}", callback_data=f"bet_{match_id}_{prediction}_{a}"))
        if (i + 1) % 3 == 0: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ مبلغ دلخواه", callback_data=f"betcustom_{match_id}_{prediction}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"match_{match_id}")])
    return InlineKeyboardMarkup(buttons)

def confirm_bet_inline(match_id, prediction, amount, option_text):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ تایید ({amount} سکه - {option_text})",
                              callback_data=f"confirm_{match_id}_{prediction}_{amount}")],
        [InlineKeyboardButton("❌ انصراف", callback_data=f"match_{match_id}")],
    ])

def admin_matches_inline(matches):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{STATUS_EMOJI.get(m['status'],'⚪')} #{m['id']} | {m['caption'][:40]}",
                              callback_data=f"adm_match_{m['id']}")]
        for m in matches])

def admin_match_actions(match):
    mid = match["id"]
    buttons = []
    if match["status"] == "upcoming":
        buttons.append([
            InlineKeyboardButton("🔒 بستن شرط‌بندی", callback_data=f"closebet_{mid}"),
            InlineKeyboardButton("🏁 ثبت نتیجه", callback_data=f"setresult_{mid}"),
        ])
    elif match["status"] == "closed":
        buttons.append([
            InlineKeyboardButton("🔓 باز کردن", callback_data=f"reopenbet_{mid}"),
            InlineKeyboardButton("🏁 ثبت نتیجه", callback_data=f"setresult_{mid}"),
        ])
    buttons.append([InlineKeyboardButton("📊 پیش‌بینی‌ها", callback_data=f"matchpreds_{mid}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm_matches_list")])
    return InlineKeyboardMarkup(buttons)

def result_inline(match):
    mid = match["id"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟠 {match['option_1']}", callback_data=f"result_{mid}_option_1")],
        [InlineKeyboardButton(f"🤝 {match['option_2']}", callback_data=f"result_{mid}_option_2")],
        [InlineKeyboardButton(f"🟡 {match['option_3']}", callback_data=f"result_{mid}_option_3")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"adm_match_{mid}")],
    ])

def users_list_inline(users):
    buttons = []
    for u in users:
        if u["special_name"]: label = f"✨ {u['special_name']} | 💰{u['coins']}"
        elif u["first_name"]: label = f"👤 {u['first_name']} | 🆔{u['user_id']}"
        else: label = f"🆔 {u['user_id']}"
        if u["is_banned"]: label = f"🚫 {label}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"usr_{u['user_id']}")])
    return InlineKeyboardMarkup(buttons)

def user_detail_inline(user):
    uid = user["user_id"]
    ban_text = "🔓 رفع بن" if user["is_banned"] else "🚫 بن"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 افزودن سکه", callback_data=f"usradd_{uid}"),
         InlineKeyboardButton("📤 کسر سکه", callback_data=f"usrsub_{uid}")],
        [InlineKeyboardButton("💰 تنظیم سکه", callback_data=f"usrset_{uid}")],
        [InlineKeyboardButton(ban_text, callback_data=f"usrban_{uid}")],
        [InlineKeyboardButton("🔙 لیست", callback_data="usrlist")],
    ])