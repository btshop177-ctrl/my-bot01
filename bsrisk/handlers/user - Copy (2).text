import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from database import db
from keyboards import (
    admin_main_menu, channel_management_menu,
    cancel_keyboard, channels_list_inline,
    user_management_menu, users_list_inline
)
from utils import user_mention, get_display_name, escape_html

router = Router()


# ═══════ States ═══════
class AddChannelState(StatesGroup):
    waiting_for_channel = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()


class EditUserNameState(StatesGroup):
    selecting_user = State()
    waiting_for_new_name = State()


class EditBalanceState(StatesGroup):
    selecting_user = State()
    waiting_for_amount = State()


class BanUserState(StatesGroup):
    selecting_user = State()


class UnbanUserState(StatesGroup):
    selecting_user = State()


def is_admin_pv(message: Message) -> bool:
    return message.from_user.id in ADMIN_IDS and message.chat.type == "private"


# ═══════ بازگشت‌ها ═══════
@router.message(F.text == "🔙 بازگشت به پنل ادمین", F.chat.type == "private")
async def back_to_admin(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return
    await state.clear()
    await message.answer("🔧 پنل مدیریت", reply_markup=admin_main_menu())


@router.message(F.text == "❌ انصراف", F.chat.type == "private")
async def cancel_action_msg(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in ADMIN_IDS:
        await message.answer("❌ عملیات لغو شد.", reply_markup=admin_main_menu())
    else:
        from keyboards import user_main_menu
        await message.answer("❌ عملیات لغو شد.", reply_markup=user_main_menu())


@router.callback_query(F.data == "cancel_action")
async def cancel_action_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text("❌ عملیات لغو شد.")
    await callback.message.answer("🔧 پنل مدیریت", reply_markup=admin_main_menu())
    await callback.answer()


# ═══════ آمار ═══════
@router.message(F.text == "📊 آمار ربات", F.chat.type == "private")
async def bot_stats(message: Message):
    if not is_admin_pv(message):
        return
    user_count = await db.get_user_count()
    channels = await db.get_all_channels()
    await message.answer(
        f"📊 <b>آمار ربات</b>\n\n"
        f"👥 تعداد کاربران: <b>{user_count}</b>\n"
        f"📢 تعداد کانال‌ها: <b>{len(channels)}</b>",
        parse_mode="HTML"
    )


# ═══════ لیست کاربران ═══════
@router.message(F.text == "👥 لیست کاربران", F.chat.type == "private")
async def list_users(message: Message):
    if not is_admin_pv(message):
        return

    users = await db.get_all_users()
    if not users:
        await message.answer("❌ هنوز کاربری ثبت نشده!")
        return

    text = "👥 <b>لیست کاربران:</b>\n\n"
    none_counter = 0

    for i, user in enumerate(users[:50], 1):
        uid = user['user_id']

        if user['full_name'] and escape_html(user['full_name']):
            display = user['full_name']
        elif user['username']:
            display = f"@{user['username']}"
        else:
            none_counter += 1
            display = f"None{none_counter}"

        mention = user_mention(uid, display)
        banned = " 🚫" if user['is_banned'] else ""
        text += f"{i}. {mention} | <code>{uid}</code>{banned}\n"

    if len(users) > 50:
        text += f"\n... و <b>{len(users) - 50}</b> کاربر دیگر"

    text += f"\n\n📊 مجموع: <b>{len(users)}</b> کاربر"

    await message.answer(text, parse_mode="HTML")


# ═══════════════════════════════════════
#          مدیریت کانال‌ها
# ═══════════════════════════════════════

@router.message(F.text == "📢 مدیریت کانال‌ها", F.chat.type == "private")
async def channel_management(message: Message):
    if not is_admin_pv(message):
        return
    await message.answer(
        "📢 <b>مدیریت کانال‌های جوین اجباری</b>",
        reply_markup=channel_management_menu(),
        parse_mode="HTML"
    )


@router.message(F.text == "➕ افزودن کانال", F.chat.type == "private")
async def add_channel_start(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return
    await state.set_state(AddChannelState.waiting_for_channel)
    await message.answer(
        "📢 <b>افزودن کانال جدید</b>\n\n"
        "آیدی عددی یا یوزرنیم کانال:\n\n"
        "<code>-1001234567890</code>\n"
        "<code>@channel_username</code>\n\n"
        "⚠️ ربات باید ادمین کانال باشد!",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AddChannelState.waiting_for_channel, F.chat.type == "private")
async def add_channel_process(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_pv(message):
        return

    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("❌ لغو شد.", reply_markup=admin_main_menu())
        return

    channel_input = message.text.strip()
    try:
        chat = await bot.get_chat(channel_input)
        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            await message.answer("⚠️ ربات ادمین این کانال نیست!", reply_markup=channel_management_menu())
            await state.clear()
            return

        invite_link = None
        if chat.username:
            invite_link = f"https://t.me/{chat.username}"
        else:
            try:
                link_obj = await bot.create_chat_invite_link(chat.id)
                invite_link = link_obj.invite_link
            except Exception:
                invite_link = chat.invite_link

        await db.add_channel(str(chat.id), chat.title or "بدون نام",
                             chat.username or "", invite_link or "", message.from_user.id)
        await state.clear()
        await message.answer(
            f"✅ <b>کانال اضافه شد!</b>\n\n"
            f"📢 {escape_html(chat.title or '')}\n🆔 <code>{chat.id}</code>",
            reply_markup=channel_management_menu(), parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"❌ خطا: <code>{escape_html(str(e))}</code>",
            reply_markup=channel_management_menu(), parse_mode="HTML"
        )
        await state.clear()


@router.message(F.text == "📋 لیست کانال‌ها", F.chat.type == "private")
async def list_channels(message: Message):
    if not is_admin_pv(message):
        return
    channels = await db.get_all_channels()
    if not channels:
        await message.answer("📢 هیچ کانالی ثبت نشده.")
        return
    text = "📢 <b>لیست کانال‌ها:</b>\n\n"
    for i, ch in enumerate(channels, 1):
        username = f"@{ch['channel_username']}" if ch['channel_username'] else "ندارد"
        title = escape_html(ch['channel_title'] or "")
        text += f"{i}. <b>{title}</b>\n   🆔 <code>{ch['channel_id']}</code> | {username}\n\n"
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "➖ حذف کانال", F.chat.type == "private")
async def remove_channel_start(message: Message):
    if not is_admin_pv(message):
        return
    channels = await db.get_all_channels()
    if not channels:
        await message.answer("📢 هیچ کانالی برای حذف نیست.")
        return
    await message.answer("🗑 <b>کانال برای حذف:</b>",
                         reply_markup=channels_list_inline(channels), parse_mode="HTML")


@router.callback_query(F.data.startswith("remove_ch:"))
async def remove_channel_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
        return
    channel_id = callback.data.split(":")[1]
    channel = await db.get_channel(channel_id)
    if channel:
        await db.remove_channel(channel_id)
        title = escape_html(channel['channel_title'] or "")
        await callback.message.edit_text(f"✅ <b>{title}</b> حذف شد!", parse_mode="HTML")
    else:
        await callback.message.edit_text("❌ یافت نشد!")
    await callback.answer()


# ═══════════════════════════════════════
#          مدیریت کاربران
# ═══════════════════════════════════════

@router.message(F.text == "🔧 مدیریت کاربر", F.chat.type == "private")
async def user_management(message: Message):
    if not is_admin_pv(message):
        return
    await message.answer("🔧 <b>مدیریت کاربران</b>", reply_markup=user_management_menu(), parse_mode="HTML")


async def show_users_list(message_or_cb, action: str, action_title: str, state: FSMContext, page: int = 0):
    users = await db.get_all_users()
    if not users:
        if isinstance(message_or_cb, Message):
            await message_or_cb.answer("❌ هیچ کاربری ثبت نشده!")
        else:
            await message_or_cb.message.edit_text("❌ هیچ کاربری ثبت نشده!")
        return

    text = (
        f"👥 <b>{action_title}</b>\n\n"
        f"کاربر مورد نظر را انتخاب کنید:\n"
        f"📊 مجموع: <b>{len(users)}</b> کاربر"
    )
    keyboard = users_list_inline(users, action=action, page=page)

    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message_or_cb.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("users_page:"))
async def users_pagination(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1]
    page = int(parts[2])

    titles = {
        "edit_name": "✏️ ویرایش نام بازیکن",
        "edit_balance": "💰 ویرایش سکه",
        "ban": "🚫 بن کاربر",
        "unban": "✅ آنبن کاربر",
    }

    await show_users_list(callback, action, titles.get(action, ""), state, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("sel_user:"))
async def user_selected(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1]
    target_id = int(parts[2])

    user = await db.get_user(target_id)
    if not user:
        await callback.answer("❌ کاربر یافت نشد!", show_alert=True)
        return

    await state.update_data(target_id=target_id)
    display_name = get_display_name(user)
    mention = user_mention(target_id, display_name)

    if action == "edit_name":
        current = escape_html(user['game_name'] or "تعیین نشده")
        await state.set_state(EditUserNameState.waiting_for_new_name)
        await callback.message.delete()
        await callback.message.answer(
            f"✏️ <b>ویرایش نام بازیکن</b>\n\n"
            f"👤 کاربر: {mention}\n"
            f"🎮 نام فعلی: <b>{current}</b>\n\n"
            f"📌 قوانین:\n"
            f"• فقط حروف انگلیسی (a-z)\n"
            f"• 3 تا 16 حرف\n\n"
            f"👇 نام جدید را بفرستید:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )

    elif action == "edit_balance":
        await state.set_state(EditBalanceState.waiting_for_amount)
        await callback.message.delete()
        await callback.message.answer(
            f"💰 <b>ویرایش سکه</b>\n\n"
            f"👤 کاربر: {mention}\n"
            f"💳 موجودی فعلی: <b>{user['balance']:,.0f}</b>\n\n"
            f"👇 مقدار جدید را بفرستید:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )

    elif action == "ban":
        if target_id in ADMIN_IDS:
            await callback.answer("⚠️ نمیتوان ادمین را بن کرد!", show_alert=True)
            return
        if user['is_banned']:
            await callback.answer("⚠️ این کاربر از قبل بن است!", show_alert=True)
            return

        await db.set_banned(target_id, True)
        await state.clear()
        await callback.message.edit_text(
            f"🚫 کاربر {mention} با موفقیت مسدود شد!",
            parse_mode="HTML"
        )
        await callback.message.answer("🔧 مدیریت", reply_markup=user_management_menu())

    elif action == "unban":
        if not user['is_banned']:
            await callback.answer("⚠️ این کاربر بن نیست!", show_alert=True)
            return

        await db.set_banned(target_id, False)
        await state.clear()
        await callback.message.edit_text(
            f"✅ کاربر {mention} با موفقیت آزاد شد!",
            parse_mode="HTML"
        )
        await callback.message.answer("🔧 مدیریت", reply_markup=user_management_menu())

    await callback.answer()


@router.message(F.text == "✏️ ویرایش نام کاربر", F.chat.type == "private")
async def edit_name_start(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return
    await state.set_state(EditUserNameState.selecting_user)
    await show_users_list(message, "edit_name", "✏️ ویرایش نام بازیکن", state)


@router.message(EditUserNameState.waiting_for_new_name, F.chat.type == "private")
async def edit_name_process(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return

    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("❌ لغو شد.", reply_markup=user_management_menu())
        return

    name = message.text.strip() if message.text else ""
    if not re.match(r'^[a-zA-Z]{3,16}$', name):
        await message.answer("❌ نام نامعتبر! فقط 3-16 حرف انگلیسی.")
        return

    data = await state.get_data()
    target_id = data.get('target_id')
    if not target_id:
        await state.clear()
        await message.answer("❌ خطا! دوباره تلاش کنید.", reply_markup=user_management_menu())
        return

    exists = await db.get_game_name_exists(name, exclude_user_id=target_id)
    if exists:
        await message.answer(f"❌ نام <b>{name}</b> قبلاً انتخاب شده!", parse_mode="HTML")
        return

    await db.set_game_name(target_id, name)
    await state.clear()

    user = await db.get_user(target_id)
    display_name = get_display_name(user)
    mention = user_mention(target_id, display_name)
    await message.answer(
        f"✅ نام بازیکن کاربر {mention} به <b>{name}</b> تغییر کرد!",
        reply_markup=user_management_menu(), parse_mode="HTML"
    )


@router.message(F.text == "💰 ویرایش سکه", F.chat.type == "private")
async def edit_balance_start(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return
    await state.set_state(EditBalanceState.selecting_user)
    await show_users_list(message, "edit_balance", "💰 ویرایش سکه", state)


@router.message(EditBalanceState.waiting_for_amount, F.chat.type == "private")
async def edit_balance_process(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return

    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("❌ لغو شد.", reply_markup=user_management_menu())
        return

    try:
        amount = float(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("❌ مقدار باید عدد باشد!")
        return

    if amount < 0:
        await message.answer("❌ مقدار نمیتواند منفی باشد!")
        return

    data = await state.get_data()
    target_id = data.get('target_id')
    if not target_id:
        await state.clear()
        await message.answer("❌ خطا!", reply_markup=user_management_menu())
        return

    await db.set_balance(target_id, amount)
    await state.clear()

    user = await db.get_user(target_id)
    display_name = get_display_name(user)
    mention = user_mention(target_id, display_name)
    await message.answer(
        f"✅ موجودی {mention} به <b>{amount:,.0f}</b> سکه تغییر کرد!",
        reply_markup=user_management_menu(), parse_mode="HTML"
    )


@router.message(F.text == "🚫 بن کاربر", F.chat.type == "private")
async def ban_user_start(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return
    await state.set_state(BanUserState.selecting_user)
    await show_users_list(message, "ban", "🚫 بن کاربر", state)


@router.message(F.text == "✅ آنبن کاربر", F.chat.type == "private")
async def unban_user_start(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return
    await state.set_state(UnbanUserState.selecting_user)
    await show_users_list(message, "unban", "✅ آنبن کاربر", state)


# ═══════ ارسال همگانی ═══════
@router.message(F.text == "📨 ارسال همگانی", F.chat.type == "private")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin_pv(message):
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("📨 پیام همگانی را بفرستید:", reply_markup=cancel_keyboard())


@router.message(BroadcastState.waiting_for_message, F.chat.type == "private")
async def broadcast_process(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_pv(message):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("❌ لغو شد.", reply_markup=admin_main_menu())
        return

    await state.clear()
    users = await db.get_all_users()
    success = 0
    failed = 0
    status_msg = await message.answer("📨 در حال ارسال...")

    for user in users:
        try:
            await message.copy_to(chat_id=user["user_id"])
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"📨 <b>تمام شد!</b>\n✅ {success} | ❌ {failed}",
        parse_mode="HTML"
    )
    await message.answer("🔧 پنل مدیریت", reply_markup=admin_main_menu())