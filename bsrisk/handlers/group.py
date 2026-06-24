from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_IDS, MUTE_DURATION
from database import db
from keyboards import join_channels_keyboard

router = Router()


async def check_user_joined(bot: Bot, user_id: int) -> list:
    """بررسی عضویت کاربر در کانال‌های اجباری"""
    channels = await db.get_all_channels()
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(
                chat_id=int(ch["channel_id"]),
                user_id=user_id
            )
            if member.status in ["left", "kicked"]:
                not_joined.append(ch)
        except Exception:
            pass
    return not_joined


async def is_admin_in_group(bot: Bot, chat_id: int, user_id: int) -> bool:
    """بررسی آیا کاربر ادمین گروه هست"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False


def extract_user_id_after_command(text: str) -> int | None:
    """استخراج آیدی عددی از انتهای متن دستور"""
    parts = text.strip().split()
    for part in reversed(parts):
        try:
            uid = int(part)
            if uid > 0:
                return uid
        except ValueError:
            continue
    return None


# ═══════════════════════════════════════
#           کانال‌ها (بی‌توجه)
# ═══════════════════════════════════════
@router.channel_post()
@router.edited_channel_post()
async def channel_post_handler(message: Message):
    """در کانال هیچ کاری نمیکنه"""
    return


# ═══════════════════════════════════════
#           هندلر گروه‌ها
# ═══════════════════════════════════════
@router.message(F.chat.type.in_({"group", "supergroup"}))
async def group_message_handler(message: Message, bot: Bot):
    if message.from_user is None or message.from_user.is_bot:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    # ثبت گروه
    await db.add_group(chat_id, message.chat.title or "")

    text = message.text or message.caption or ""

    # ═══════════════════════════════════════
    #            دستورات ادمین
    # ═══════════════════════════════════════
    is_user_admin = user_id in ADMIN_IDS or await is_admin_in_group(bot, chat_id, user_id)

    if is_user_admin:
        # ══ سکوت ══
        if text.startswith("سکوت"):
            if chat_type != "supergroup":
                await message.reply(
                    "⚠️ <b>قابلیت سکوت فقط در سوپرگروه‌ها کار میکنه!</b>\n\n"
                    "📌 برای تبدیل گروه به سوپرگروه:\n"
                    "• تنظیمات گروه → یوزرنیم عمومی تنظیم کنید\n"
                    "• یا History رو Visible کنید",
                    parse_mode="HTML"
                )
                return

            target_id = None

            if message.reply_to_message and message.reply_to_message.from_user:
                target_id = message.reply_to_message.from_user.id
            else:
                target_id = extract_user_id_after_command(text)

            if not target_id:
                await message.reply(
                    "❌ روی پیام کاربر <b>ریپلای</b> کنید\n"
                    "یا آیدی عددی بنویسید:\n\n"
                    "<code>سکوت 123456789</code>",
                    parse_mode="HTML"
                )
                return

            if target_id in ADMIN_IDS:
                await message.reply("⚠️ نمی‌توان ادمین ربات را سکوت کرد!")
                return

            if await is_admin_in_group(bot, chat_id, target_id):
                await message.reply("⚠️ نمی‌توان ادمین گروه را سکوت کرد!")
                return

            try:
                until_date = datetime.now() + timedelta(seconds=MUTE_DURATION)
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=target_id,
                    permissions=ChatPermissions(
                        can_send_messages=False,
                        can_send_media_messages=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False,
                        can_send_polls=False,
                    ),
                    until_date=until_date
                )
                hours = MUTE_DURATION // 3600
                await message.reply(
                    f"🔇 کاربر <a href='tg://user?id={target_id}'>کاربر</a> "
                    f"به مدت <b>{hours} ساعت</b> سکوت شد.",
                    parse_mode="HTML"
                )
            except TelegramBadRequest as e:
                err_text = str(e).lower()
                if "supergroup" in err_text:
                    await message.reply(
                        "⚠️ این گروه عادی است! ابتدا به سوپرگروه تبدیلش کنید.",
                        parse_mode="HTML"
                    )
                elif "not enough rights" in err_text or "rights" in err_text:
                    await message.reply(
                        "⚠️ <b>ربات دسترسی کافی ندارد!</b>\n"
                        "ربات رو ادمین کنید با دسترسی <b>Restrict Members</b>.",
                        parse_mode="HTML"
                    )
                else:
                    await message.reply(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")
            except Exception as e:
                await message.reply(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")
            return

        # ══ حذف سکوت ══
        if text.startswith("حذف سکوت"):
            if chat_type != "supergroup":
                await message.reply("⚠️ این قابلیت فقط در سوپرگروه‌ها کار میکنه!")
                return

            target_id = None
            if message.reply_to_message and message.reply_to_message.from_user:
                target_id = message.reply_to_message.from_user.id
            else:
                target_id = extract_user_id_after_command(text)

            if not target_id:
                await message.reply(
                    "❌ روی پیام کاربر <b>ریپلای</b> کنید\n"
                    "یا آیدی بنویسید: <code>حذف سکوت 123456789</code>",
                    parse_mode="HTML"
                )
                return

            try:
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=target_id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True,
                        can_send_polls=True,
                        can_invite_users=True,
                    )
                )
                await message.reply(
                    f"🔊 سکوت کاربر <a href='tg://user?id={target_id}'>کاربر</a> برداشته شد.",
                    parse_mode="HTML"
                )
            except Exception as e:
                await message.reply(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")
            return

        # ادمین چیز دیگه‌ای نوشت → بی‌توجه
        return

    # ═══════════════════════════════════════
    #     کاربر عادی: بررسی عضویت اجباری
    # ═══════════════════════════════════════
    not_joined = await check_user_joined(bot, user_id)

    if not_joined:
        # حذف پیام کاربر
        try:
            await message.delete()
        except Exception:
            pass

        # ارسال هشدار با حذف کیبورد قبلی (selective برای کاربر خاص)
        keyboard = join_channels_keyboard(not_joined)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ <a href='tg://user?id={user_id}'>{message.from_user.full_name}</a> عزیز،\n\n"
                    f"برای چت در این گروه باید در کانال‌های زیر عضو شوید:"
                ),
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception:
            pass

    # اگه عضو هست → کاری نکن (پیامش رو نگه دار)