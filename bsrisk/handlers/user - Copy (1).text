import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards import user_main_menu, cancel_keyboard, admin_main_menu
from config import ADMIN_IDS
from utils import user_mention, escape_html

router = Router()


class SetNameState(StatesGroup):
    waiting_for_name = State()


class ChangeNameState(StatesGroup):
    waiting_for_new_name = State()


def validate_game_name(name: str) -> tuple[bool, str]:
    if len(name) < 3:
        return False, "❌ نام باید حداقل <b>3 حرف</b> باشد!"
    if len(name) > 16:
        return False, "❌ نام باید حداکثر <b>16 حرف</b> باشد!"
    if not re.match(r'^[a-zA-Z]+$', name):
        return False, "❌ فقط <b>حروف انگلیسی</b> (a-z) مجاز است!"
    return True, ""


# ═══════ استارت ═══════
@router.message(CommandStart(), F.chat.type == "private")
async def start_command(message: Message, state: FSMContext):
    user = message.from_user
    await state.clear()

    existing = await db.get_user(user.id)
    if not existing:
        await db.add_user(user.id, user.username or "", user.full_name or "")
    else:
        await db.update_user_info(user.id, user.username or "", user.full_name or "")

    if user.id in ADMIN_IDS:
        mention = user_mention(user.id, user.full_name)
        await message.answer(
            f"سلام {mention} 👋\n\n🔧 <b>پنل مدیریت ربات</b>",
            reply_markup=admin_main_menu(),
            parse_mode="HTML"
        )
        return

    user_data = await db.get_user(user.id)
    if user_data and user_data['is_banned']:
        await message.answer(
            "⛔ <b>حساب شما مسدود شده است!</b>",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"
        )
        return

    if not user_data or not user_data['game_name']:
        await state.set_state(SetNameState.waiting_for_name)
        await message.answer(
            "🎮 <b>به ربات خوش آمدید!</b>\n\n"
            "لطفاً یک <b>نام بازیکن</b> انتخاب کنید:\n\n"
            "📌 قوانین:\n"
            "• فقط <b>حروف انگلیسی</b> (a-z)\n"
            "• <b>3</b> تا <b>16</b> حرف\n\n"
            "👇 نام را بفرستید:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"
        )
        return

    mention = user_mention(user.id, user_data['game_name'])
    await message.answer(
        f"سلام {mention} 👋\n\nبه ربات خوش آمدید! ✨",
        reply_markup=user_main_menu(),
        parse_mode="HTML"
    )


@router.message(SetNameState.waiting_for_name, F.chat.type == "private")
async def process_game_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    is_valid, error_msg = validate_game_name(name)
    if not is_valid:
        await message.answer(f"{error_msg}\n\n👇 دوباره بفرستید:", parse_mode="HTML")
        return

    exists = await db.get_game_name_exists(name)
    if exists:
        await message.answer(
            f"❌ نام <b>{name}</b> قبلاً انتخاب شده!\n👇 نام دیگری بفرستید:",
            parse_mode="HTML"
        )
        return

    await db.set_game_name(message.from_user.id, name)
    await state.clear()

    mention = user_mention(message.from_user.id, name)
    await message.answer(
        f"✅ نام بازیکن ثبت شد!\n\n🎮 نام: {mention}\n\n🎉 خوش آمدید!",
        reply_markup=user_main_menu(),
        parse_mode="HTML"
    )


@router.message(F.text == "✏️ تغییر نام", F.chat.type == "private")
async def change_name_start(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_IDS:
        return

    user_data = await db.get_user(message.from_user.id)
    if not user_data:
        await message.answer("❌ ابتدا /start بزنید.")
        return

    current = escape_html(user_data['game_name'] or "None")
    await state.set_state(ChangeNameState.waiting_for_new_name)
    await message.answer(
        f"✏️ <b>تغییر نام بازیکن</b>\n\n"
        f"نام فعلی: <b>{current}</b>\n\n"
        f"📌 قوانین:\n"
        f"• فقط حروف انگلیسی (a-z)\n"
        f"• 3 تا 16 حرف\n\n"
        f"👇 نام جدید را بفرستید:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(ChangeNameState.waiting_for_new_name, F.chat.type == "private")
async def change_name_process(message: Message, state: FSMContext):
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("❌ لغو شد.", reply_markup=user_main_menu())
        return

    name = message.text.strip() if message.text else ""
    is_valid, error_msg = validate_game_name(name)
    if not is_valid:
        await message.answer(f"{error_msg}\n\n👇 دوباره:", parse_mode="HTML")
        return

    exists = await db.get_game_name_exists(name, exclude_user_id=message.from_user.id)
    if exists:
        await message.answer(
            f"❌ نام <b>{name}</b> قبلاً انتخاب شده!\n👇 نام دیگری:",
            parse_mode="HTML"
        )
        return

    await db.set_game_name(message.from_user.id, name)
    await state.clear()

    mention = user_mention(message.from_user.id, name)
    await message.answer(
        f"✅ نام شما به {mention} تغییر کرد!",
        reply_markup=user_main_menu(),
        parse_mode="HTML"
    )


# ═══════ بررسی عضویت ═══════
@router.callback_query(F.data == "check_join")
async def check_join_callback(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id

    if callback.message.chat.type in ["group", "supergroup"]:
        channels = await db.get_all_channels()
        not_joined = []
        for ch in channels:
            try:
                member = await bot.get_chat_member(int(ch["channel_id"]), user_id)
                if member.status in ["left", "kicked"]:
                    not_joined.append(ch)
            except Exception:
                pass

        if not_joined:
            await callback.answer(
                "🔔 شما هنوز در همه کانال‌ها عضو نشدید!\n"
                "ابتدا عضو شوید و دوباره بزنید.",
                show_alert=True
            )
        else:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.answer("✅ عضویت تأیید شد!", show_alert=True)
        return

    channels = await db.get_all_channels()
    if not channels:
        await callback.message.edit_text("✅ محدودیتی وجود ندارد!")
        await callback.answer()
        return

    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(int(ch["channel_id"]), user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append(ch)
        except Exception:
            pass

    if not_joined:
        await callback.answer(
            "🔔 لطفاً ابتدا در کانال‌ها عضو شوید و سپس\n"
            "دکمه را فشار دهید!\n\n"
            "❗ اگر عضو شدید و هنوز این پیام را\n"
            "مشاهده میکنید , با ادمین تماس بگیرید!",
            show_alert=True
        )
        return

    await callback.message.edit_text("✅ <b>عضویت تأیید شد!</b>", parse_mode="HTML")
    await callback.answer()

    user_data = await db.get_user(user_id)
    if not user_data or not user_data['game_name']:
        await state.set_state(SetNameState.waiting_for_name)
        await callback.message.answer(
            "🎮 <b>حالا یک نام بازیکن انتخاب کنید:</b>\n\n"
            "📌 فقط حروف انگلیسی | 3 تا 16 حرف\n\n"
            "👇 نام را بفرستید:",
            parse_mode="HTML"
        )
    else:
        mention = user_mention(user_id, user_data['game_name'])
        await callback.message.answer(
            f"سلام {mention} 👋\nخوش آمدید! ✨",
            reply_markup=user_main_menu(),
            parse_mode="HTML"
        )


# ═══════ حساب کاربری ═══════
@router.message(F.text == "👤 حساب کاربری", F.chat.type == "private")
async def user_profile(message: Message):
    if message.from_user.id in ADMIN_IDS:
        return

    user_data = await db.get_user(message.from_user.id)
    if not user_data:
        await message.answer("❌ /start بزنید.")
        return

    game_name = user_data['game_name'] or "None"
    mention = user_mention(message.from_user.id, game_name)
    await message.answer(
        f"👤 <b>حساب کاربری شما</b>\n\n"
        f"🎮 نام: {mention}\n"
        f"💰 موجودی: <b>{user_data['balance']:,.0f}</b> سکه",
        parse_mode="HTML"
    )


@router.message(F.text == "💰 موجودی", F.chat.type == "private")
async def user_balance(message: Message):
    if message.from_user.id in ADMIN_IDS:
        return

    user_data = await db.get_user(message.from_user.id)
    if not user_data:
        await message.answer("❌ /start بزنید.")
        return
    await message.answer(
        f"💰 <b>موجودی: {user_data['balance']:,.0f} سکه</b>\n\n"
        f"🔜 شارژ و برداشت به زودی...",
        parse_mode="HTML"
    )


@router.message(F.text == "📋 راهنما", F.chat.type == "private")
async def help_command(message: Message):
    if message.from_user.id in ADMIN_IDS:
        return

    await message.answer(
        "📋 <b>راهنما</b>\n\n"
        "👤 حساب کاربری\n"
        "💰 موجودی\n"
        "✏️ تغییر نام بازیکن\n\n"
        "🔜 بخش‌های بیشتر به زودی...",
        parse_mode="HTML"
    )