from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, ChatPermissions, Message

from config import MUTE_DURATION
from database import db
from keyboards import (
    group_admin_panel_keyboard,
    group_join_settings_keyboard,
    group_permissions_keyboard,
)
from utils import escape_html

router = Router()
GROUP_TYPES = {"group", "supergroup"}


async def is_admin_in_group(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in {"administrator", "creator"}
    except Exception:
        return False


async def check_user_joined(bot: Bot, user_id: int) -> list:
    """سازگاری با نسخه قبلی: بررسی کانال‌های جوین اجباری PV."""
    channels = await db.get_all_channels()
    not_joined = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(int(channel["channel_id"]), user_id)
            if member.status in {"left", "kicked"} or getattr(member, "is_member", True) is False:
                not_joined.append(channel)
        except Exception:
            continue
    return not_joined


async def is_owner_in_group(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status == "creator"
    except Exception:
        return False


async def has_group_permission(bot: Bot, chat_id: int, user_id: int, permission: str) -> bool:
    """فقط مالک گروه یا ادمینی که مالک مجوز گرفته است."""
    if await is_owner_in_group(bot, chat_id, user_id):
        return True
    if not await is_admin_in_group(bot, chat_id, user_id):
        return False
    return await db.has_group_permission(chat_id, user_id, permission)


def command_name(text: str) -> str:
    first = (text or "").split(maxsplit=1)[0].lower()
    return first.split("@", maxsplit=1)[0].lstrip("/")


def command_action(text: str) -> tuple[str, str]:
    """تشخیص دستور فارسی فقط در ابتدای پیام.

    عبارت‌هایی مثل «پنل تو اول چک کن» عمداً دستور محسوب نمی‌شوند؛
    پنل فقط وقتی اجرا می‌شود که کل پیام دقیقاً «پنل» باشد.
    """
    normalized = (text or "").strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
        if not normalized:
            return "", ""
        first, *rest = normalized.split(maxsplit=1)
        first = first.split("@", maxsplit=1)[0]
        normalized = first + ((" " + rest[0]) if rest else "")

    commands = [
        ("تنظیمات گروه", "panel"), ("پنل گروه", "panel"), ("پنل", "panel"),
        ("جوین روشن", "join_on"), ("جوین خاموش", "join_off"),
        ("جوین اضافه", "join_add"), ("جوین حذف", "join_remove"),
        ("لیست جوین", "join_list"),
        ("اعطای مدیریت", "grant_manage"), ("اعطای جوین", "grant_join"),
        ("اعطای بن", "grant_ban"), ("لغو مدیریت", "revoke_manage"),
        ("لغو جوین", "revoke_join"), ("لغو بن", "revoke_ban"),
        ("رفع سکوت", "unmute"), ("حذف سکوت", "unmute"),
        ("رفع بن", "unban"), ("بن", "ban"), ("سکوت", "mute"),
        # نام‌های انگلیسی قبلی برای سازگاری نگه داشته شده‌اند، اما در راهنما
        # و دکمه‌ها فقط معادل فارسی نمایش داده می‌شود.
        ("group_panel", "panel"), ("settings", "panel"), ("panel", "panel"),
        ("join_on", "join_on"), ("join_off", "join_off"),
        ("join_add", "join_add"), ("join_remove", "join_remove"),
        ("join_list", "join_list"), ("grant_ban", "grant_ban"),
        ("grant_join", "grant_join"), ("grant_manage", "grant_manage"),
        ("revoke_ban", "revoke_ban"), ("revoke_join", "revoke_join"),
        ("revoke_manage", "revoke_manage"), ("ban", "ban"),
        ("unban", "unban"), ("mute", "mute"), ("unmute", "unmute"),
    ]
    for phrase, action in sorted(commands, key=lambda item: len(item[0]), reverse=True):
        if normalized == phrase:
            return action, ""
        if normalized.startswith(phrase + " "):
            return action, normalized[len(phrase):].strip()
    return "", ""


def is_valid_target_arguments(message: Message, arguments: str) -> bool:
    """برای جلوگیری از واکنش به جمله‌هایی مثل «بن تو اول چک کن»."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return not arguments or arguments.isdigit()
    return not arguments or arguments.isdigit()


def extract_user_id_after_command(text: str) -> int | None:
    """آیدی عددی را از دستور یا پیام ریپلای‌شده استخراج می‌کند."""
    for part in reversed((text or "").strip().split()):
        try:
            user_id = int(part)
            if user_id > 0:
                return user_id
        except ValueError:
            continue
    return None


def target_user_id(message: Message) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    return extract_user_id_after_command(message.text or message.caption or "")


async def ensure_group_record(message: Message, bot: Bot, user_is_owner: bool = False):
    await db.add_group(
        message.chat.id,
        message.chat.title or "",
        owner_id=message.from_user.id if user_is_owner else None,
    )


async def group_channels_not_joined(bot: Bot, group_id: int, user_id: int) -> list:
    channels = await db.get_group_channels(group_id)
    not_joined = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(int(channel["channel_id"]), user_id)
            if member.status in {"left", "kicked"} or getattr(member, "is_member", True) is False:
                not_joined.append(channel)
        except Exception:
            # خطای موقت API نباید باعث حذف اشتباه پیام شود.
            continue
    return not_joined


async def answer_permission_denied(message: Message):
    await message.reply("⛔ شما اجازه استفاده از این قابلیت را ندارید.")


# ═══════════════════════════════════════
#                کانال‌ها
# ═══════════════════════════════════════
@router.channel_post()
@router.edited_channel_post()
async def channel_post_handler(message: Message):
    # ربات در کانال هیچ پیامی، منو یا کیبوردی ایجاد نمی‌کند.
    return


# ═══════════════════════════════════════
#            دستورهای مستقیم گروه
# ═══════════════════════════════════════
async def show_group_panel(message: Message, bot: Bot, owner: bool):
    await message.reply(
        "🛠 <b>پنل مدیریت گروه</b>\n\n"
        "این پنل فقط برای مدیران گروه فعال است.",
        reply_markup=group_admin_panel_keyboard(is_owner=owner),
        parse_mode="HTML",
    )


@router.message(F.chat.type.in_(GROUP_TYPES))
async def group_message_handler(message: Message, bot: Bot):
    """در گروه فقط دستورهای مجاز مدیران اجرا می‌شوند.

    پیام عادی کاربر بدون پاسخ رها می‌شود. اگر مالک جوین اجباری را روشن کرده
    باشد، پیام کاربرِ عضو نشده بی‌صدا حذف می‌شود؛ هیچ پیام یا Reply Keyboard
    جدیدی در گروه ارسال نمی‌شود.
    """
    if not message.from_user or message.from_user.is_bot:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or message.caption or ""
    is_admin = await is_admin_in_group(bot, chat_id, user_id)
    owner = is_admin and await is_owner_in_group(bot, chat_id, user_id)
    await ensure_group_record(message, bot, user_is_owner=owner)

    # پیام‌های عادی مدیر هم پردازش نمی‌شوند؛ فقط دستورهای مشخص پایین معتبرند.
    if is_admin and text:
        action, arguments = command_action(text)

        # پنل فقط یک فرمان مستقل است؛ «پنل تو اول چک کن» فرمان نیست.
        if action == "panel":
            if not arguments:
                await show_group_panel(message, bot, owner)
            return

        if action in {
            "grant_ban", "grant_join", "grant_manage",
            "revoke_ban", "revoke_join", "revoke_manage",
        }:
            if is_valid_target_arguments(message, arguments):
                await change_admin_permission(message, bot, owner, action=action)
            return

        if action in {"join_on", "join_off", "join_add", "join_remove", "join_list"}:
            await handle_join_command(message, bot, action=action, arguments=arguments)
            return

        if action in {"ban", "unban", "mute", "unmute"}:
            if is_valid_target_arguments(message, arguments):
                if action == "ban":
                    await handle_ban_command(message, bot)
                elif action == "unban":
                    await handle_unban_command(message, bot)
                elif action == "mute":
                    await handle_mute_command(message, bot)
                else:
                    await handle_unmute_command(message, bot)
            return

    # اعمال اختیاری جوین اجباری گروه به صورت silent؛ برای عضو عادی هیچ
    # هشداری در گروه ارسال نمی‌شود.
    group = await db.get_group(chat_id)
    if group and group["forced_join_enabled"] and not is_admin:
        not_joined = await group_channels_not_joined(bot, chat_id, user_id)
        if not_joined:
            try:
                await message.delete()
            except Exception:
                pass


async def change_admin_permission(message: Message, bot: Bot, owner: bool, action: str | None = None):
    if not owner:
        await answer_permission_denied(message)
        return

    name = action or command_name(message.text or "")
    permission_by_command = {
        "grant_ban": "ban", "allow_ban": "ban",
        "grant_join": "join", "allow_join": "join",
        "grant_manage": "manage", "allow_manage": "manage",
        "revoke_ban": "ban", "deny_ban": "ban",
        "revoke_join": "join", "deny_join": "join",
        "revoke_manage": "manage", "deny_manage": "manage",
    }
    permission = permission_by_command[name]
    is_grant = name.startswith(("grant_", "allow_"))
    target_id = target_user_id(message)

    if not target_id:
        await message.reply(
            f"❌ ادمین مورد نظر را با ریپلای یا آیدی عددی مشخص کنید.\n"
            f"مثال: <code>/{name} 123456789</code>",
            parse_mode="HTML",
        )
        return
    if target_id == message.from_user.id:
        await message.reply("⚠️ مالک گروه نیازی به اعطای مجوز به خودش ندارد.")
        return
    if not await is_admin_in_group(bot, message.chat.id, target_id):
        await message.reply("❌ این کاربر در حال حاضر ادمین گروه نیست.")
        return

    if is_grant:
        await db.set_group_permission(message.chat.id, target_id, permission, message.from_user.id)
        await message.reply(f"✅ دسترسی <b>{permission}</b> برای ادمین <code>{target_id}</code> فعال شد.", parse_mode="HTML")
    else:
        await db.remove_group_permission(message.chat.id, target_id, permission)
        await message.reply(f"✅ دسترسی <b>{permission}</b> از ادمین <code>{target_id}</code> گرفته شد.", parse_mode="HTML")


async def handle_join_command(message: Message, bot: Bot, action: str | None = None,
                              arguments: str | None = None):
    command = action or command_name(message.text or "")
    if not await has_group_permission(bot, message.chat.id, message.from_user.id, "join"):
        await answer_permission_denied(message)
        return

    if command == "join_on":
        channels = await db.get_group_channels(message.chat.id)
        if not channels:
            await message.reply("❌ ابتدا با دستور <code>جوین اضافه @channel</code> یک کانال اضافه کنید.", parse_mode="HTML")
            return
        await db.set_group_forced_join(message.chat.id, True)
        await message.reply("✅ جوین اجباری این گروه روشن شد.")
        return

    if command == "join_off":
        await db.set_group_forced_join(message.chat.id, False)
        await message.reply("✅ جوین اجباری این گروه خاموش شد.")
        return

    if command == "join_list":
        channels = await db.get_group_channels(message.chat.id)
        group = await db.get_group(message.chat.id)
        status = "روشن" if group and group["forced_join_enabled"] else "خاموش"
        if not channels:
            await message.reply(f"📢 کانالی ثبت نشده است.\nوضعیت جوین اجباری: <b>{status}</b>", parse_mode="HTML")
            return
        lines = [f"📢 <b>کانال‌های جوین اجباری گروه</b> | وضعیت: {status}", ""]
        for channel in channels:
            lines.append(f"• {escape_html(channel['channel_title'] or channel['channel_id'])} — <code>{channel['channel_id']}</code>")
        await message.reply("\n".join(lines), parse_mode="HTML")
        return

    if arguments is not None:
        channel_input = arguments.strip()
    else:
        parts = (message.text or "").split(maxsplit=1)
        channel_input = parts[1].strip() if len(parts) == 2 else ""

    if not channel_input:
        usage = "جوین اضافه @channel یا جوین حذف @channel"
        await message.reply(f"❌ نام کانال را وارد کنید.\nمثال: <code>{usage}</code>", parse_mode="HTML")
        return
    try:
        chat = await bot.get_chat(channel_input)
        if chat.type not in {"channel", "supergroup"}:
            await message.reply("❌ فقط کانال یا سوپرگروه قابل ثبت است.")
            return

        if command == "join_remove":
            await db.remove_group_channel(message.chat.id, str(chat.id))
            await message.reply("✅ کانال از جوین اجباری این گروه حذف شد.")
            return

        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status not in {"administrator", "creator"}:
            await message.reply("⚠️ ربات باید در کانال ادمین باشد تا عضویت را بررسی کند.")
            return

        invite_link = f"https://t.me/{chat.username}" if chat.username else ""
        if not invite_link:
            try:
                invite_link = (await bot.create_chat_invite_link(chat.id)).invite_link
            except Exception:
                invite_link = getattr(chat, "invite_link", "") or ""

        await db.add_group_channel(
            message.chat.id,
            str(chat.id),
            chat.title or "بدون نام",
            chat.username or "",
            invite_link,
            message.from_user.id,
        )
        await message.reply(f"✅ کانال <b>{escape_html(chat.title or '')}</b> اضافه شد.", parse_mode="HTML")
    except Exception as error:
        await message.reply(f"❌ افزودن کانال ناموفق بود: <code>{escape_html(str(error))}</code>", parse_mode="HTML")


async def handle_ban_command(message: Message, bot: Bot):
    if not await has_group_permission(bot, message.chat.id, message.from_user.id, "ban"):
        await answer_permission_denied(message)
        return
    target_id = target_user_id(message)
    if not target_id:
        await message.reply("❌ روی پیام کاربر ریپلای کنید یا بنویسید: <code>بن 123456789</code>", parse_mode="HTML")
        return
    if target_id == message.from_user.id or await is_admin_in_group(bot, message.chat.id, target_id):
        await message.reply("⚠️ نمی‌توان مالک یا ادمین گروه را بن کرد.")
        return
    try:
        await bot.ban_chat_member(chat_id=message.chat.id, user_id=target_id)
        await message.reply(f"🚫 کاربر <code>{target_id}</code> بن شد.", parse_mode="HTML")
    except Exception as error:
        await message.reply(f"❌ بن انجام نشد: <code>{escape_html(str(error))}</code>", parse_mode="HTML")


async def handle_unban_command(message: Message, bot: Bot):
    if not await has_group_permission(bot, message.chat.id, message.from_user.id, "ban"):
        await answer_permission_denied(message)
        return
    target_id = target_user_id(message)
    if not target_id:
        await message.reply("❌ روی پیام کاربر ریپلای کنید یا بنویسید: <code>رفع بن 123456789</code>", parse_mode="HTML")
        return
    try:
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=target_id, only_if_banned=True)
        await message.reply(f"✅ بن کاربر <code>{target_id}</code> برداشته شد.", parse_mode="HTML")
    except Exception as error:
        await message.reply(f"❌ رفع بن انجام نشد: <code>{escape_html(str(error))}</code>", parse_mode="HTML")


async def handle_mute_command(message: Message, bot: Bot):
    if not await has_group_permission(bot, message.chat.id, message.from_user.id, "manage"):
        await answer_permission_denied(message)
        return
    if message.chat.type != "supergroup":
        await message.reply("⚠️ قابلیت سکوت فقط در سوپرگروه‌ها کار می‌کند.")
        return
    target_id = target_user_id(message)
    if not target_id:
        await message.reply("❌ روی پیام کاربر ریپلای کنید یا بنویسید: <code>سکوت 123456789</code>", parse_mode="HTML")
        return
    if target_id == message.from_user.id or await is_admin_in_group(bot, message.chat.id, target_id):
        await message.reply("⚠️ نمی‌توان مالک یا ادمین گروه را سکوت کرد.")
        return
    try:
        until_date = datetime.now() + timedelta(seconds=MUTE_DURATION)
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_send_polls=False,
            ),
            until_date=until_date,
        )
        await message.reply(f"🔇 کاربر <code>{target_id}</code> به مدت {MUTE_DURATION // 3600} ساعت سکوت شد.", parse_mode="HTML")
    except TelegramBadRequest as error:
        await message.reply(f"❌ سکوت انجام نشد: <code>{escape_html(str(error))}</code>", parse_mode="HTML")


async def handle_unmute_command(message: Message, bot: Bot):
    if not await has_group_permission(bot, message.chat.id, message.from_user.id, "manage"):
        await answer_permission_denied(message)
        return
    target_id = target_user_id(message)
    if not target_id:
        await message.reply("❌ روی پیام کاربر ریپلای کنید یا بنویسید: <code>رفع سکوت 123456789</code>", parse_mode="HTML")
        return
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_polls=True,
                can_invite_users=True,
            ),
        )
        await message.reply(f"🔊 سکوت کاربر <code>{target_id}</code> برداشته شد.", parse_mode="HTML")
    except Exception as error:
        await message.reply(f"❌ رفع سکوت انجام نشد: <code>{escape_html(str(error))}</code>", parse_mode="HTML")


# ═══════════════════════════════════════
#              کال‌بک‌های پنل
# ═══════════════════════════════════════
async def callback_group_context(callback: CallbackQuery, bot: Bot):
    if not callback.message or callback.message.chat.type not in GROUP_TYPES:
        await callback.answer("این پنل فقط داخل گروه فعال است.", show_alert=True)
        return None
    if not await is_admin_in_group(bot, callback.message.chat.id, callback.from_user.id):
        await callback.answer("⛔ فقط ادمین‌های گروه می‌توانند از پنل استفاده کنند.", show_alert=True)
        return None
    owner = await is_owner_in_group(bot, callback.message.chat.id, callback.from_user.id)
    return callback.message.chat.id, owner


@router.callback_query(F.data.startswith("grp:"))
async def group_panel_callback(callback: CallbackQuery, bot: Bot):
    context = await callback_group_context(callback, bot)
    if context is None:
        return
    group_id, owner = context
    action = callback.data.split(":")

    if action[1] == "back":
        await callback.message.edit_text(
            "🛠 <b>پنل مدیریت گروه</b>",
            reply_markup=group_admin_panel_keyboard(owner),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if action[1] == "join":
        if len(action) == 2:
            if not await has_group_permission(bot, group_id, callback.from_user.id, "join"):
                await callback.answer("⛔ مجوز مدیریت جوین اجباری را ندارید.", show_alert=True)
                return
            group = await db.get_group(group_id)
            enabled = bool(group and group["forced_join_enabled"])
            await callback.message.edit_text(
                f"⚙️ <b>جوین اجباری گروه</b>\n\nوضعیت: <b>{'روشن' if enabled else 'خاموش'}</b>",
                reply_markup=group_join_settings_keyboard(enabled),
                parse_mode="HTML",
            )
            await callback.answer()
            return

        sub_action = ":".join(action[2:])
        if sub_action in {"on", "off"}:
            if not await has_group_permission(bot, group_id, callback.from_user.id, "join"):
                await callback.answer("⛔ مجوز مدیریت جوین اجباری را ندارید.", show_alert=True)
                return
            if sub_action == "on" and not await db.get_group_channels(group_id):
                await callback.answer("ابتدا با «جوین اضافه @channel» یک کانال اضافه کنید.", show_alert=True)
                return
            await db.set_group_forced_join(group_id, sub_action == "on")
            await callback.answer("✅ وضعیت ذخیره شد.")
            enabled = sub_action == "on"
            await callback.message.edit_text(
                f"⚙️ <b>جوین اجباری گروه</b>\n\nوضعیت: <b>{'روشن' if enabled else 'خاموش'}</b>",
                reply_markup=group_join_settings_keyboard(enabled),
                parse_mode="HTML",
            )
            return

        if sub_action == "list":
            if not await has_group_permission(bot, group_id, callback.from_user.id, "join"):
                await callback.answer("⛔ مجوز مدیریت جوین اجباری را ندارید.", show_alert=True)
                return
            channels = await db.get_group_channels(group_id)
            if channels:
                text = "📢 <b>کانال‌های این گروه:</b>\n\n" + "\n".join(
                    f"• {escape_html(channel['channel_title'] or channel['channel_id'])}"
                    for channel in channels
                )
            else:
                text = "📢 هنوز کانالی برای این گروه ثبت نشده است."
            group = await db.get_group(group_id)
            await callback.message.edit_text(
                text,
                reply_markup=group_join_settings_keyboard(bool(group and group["forced_join_enabled"])),
                parse_mode="HTML",
            )
            await callback.answer()
            return

        if sub_action == "add_help":
            await callback.answer("برای افزودن: جوین اضافه @channel", show_alert=True)
            return

    if action[1] == "ban_help":
        if not await has_group_permission(bot, group_id, callback.from_user.id, "ban"):
            await callback.answer("⛔ مجوز بن کاربران را ندارید.", show_alert=True)
            return
        await callback.answer("روی پیام کاربر ریپلای کنید و «بن» یا «رفع بن» بفرستید.", show_alert=True)
        return

    if action[1] == "mute_help":
        if not await has_group_permission(bot, group_id, callback.from_user.id, "manage"):
            await callback.answer("⛔ مجوز مدیریت کاربران را ندارید.", show_alert=True)
            return
        await callback.answer("روی پیام کاربر ریپلای کنید و «سکوت» یا «رفع سکوت» بفرستید.", show_alert=True)
        return

    if action[1] == "permissions":
        if not owner:
            await callback.answer("⛔ فقط مدیر اصلی گروه می‌تواند دسترسی بدهد.", show_alert=True)
            return
        await callback.message.edit_text(
            "👥 <b>مدیریت دسترسی ادمین‌ها</b>\n\n"
            "اعطای دسترسی فقط با دستور و توسط مدیر اصلی انجام می‌شود.",
            reply_markup=group_permissions_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if action[1] == "perm":
        if not owner:
            await callback.answer("⛔ فقط مدیر اصلی گروه.", show_alert=True)
            return
        sub_action = ":".join(action[2:])
        if sub_action in {"add_help", "remove_help"}:
            prefix = "اعطای بن | اعطای جوین | اعطای مدیریت" if sub_action == "add_help" else "لغو بن | لغو جوین | لغو مدیریت"
            await callback.answer(f"ریپلای ادمین و ارسال: {prefix}", show_alert=True)
            return
        if sub_action == "list":
            rows = await db.get_group_permissions(group_id)
            if rows:
                text = "👥 <b>دسترسی‌های واگذارشده:</b>\n\n" + "\n".join(
                    f"• <code>{row['user_id']}</code> — {row['permission']}" for row in rows
                )
            else:
                text = "👥 هنوز دسترسی‌ای واگذار نشده است."
            await callback.message.edit_text(text, reply_markup=group_permissions_keyboard(), parse_mode="HTML")
            await callback.answer()
            return
