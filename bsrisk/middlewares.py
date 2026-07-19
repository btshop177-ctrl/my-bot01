from typing import Any, Awaitable, Callable, Dict, Union

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import ADMIN_IDS
from database import db
from keyboards import join_channels_keyboard


class JoinCheckMiddleware(BaseMiddleware):
    """جوین اجباری سراسری فقط برای PV.

    گروه و کانال مسیر جداگانه‌ای دارند: ربات در گروه فقط به دستورات/کال‌بک‌های
    مدیران پاسخ می‌دهد و هیچ پیام یا Reply Keyboard مربوط به جوین اجباری
    سراسری را داخل گروه ارسال نمی‌کند.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        if not hasattr(event, "from_user") or event.from_user is None:
            return await handler(event, data)

        if event.from_user.is_bot:
            return await handler(event, data)

        # نوع چت را برای Message و CallbackQuery یکسان به دست می‌آوریم.
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat
        else:
            chat = None

        # در گروه/سوپرگروه بررسی جوین سراسری PV انجام نمی‌شود. بررسی اختیاری
        # جوین همان گروه، در group handler و فقط به شکل silent انجام می‌شود.
        if chat and chat.type in {"group", "supergroup"}:
            return await handler(event, data)

        # پست کانال و هر event بدون چت خصوصی، بی‌سر و صدا رد می‌شود.
        if chat and chat.type == "channel":
            return

        user_id = event.from_user.id

        # ادمین‌های اصلی ربات محدودیت جوین/بن سراسری ندارند.
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        user_data = await db.get_user(user_id)
        if user_data and user_data["is_banned"]:
            if isinstance(event, Message):
                await event.answer(
                    "⛔ <b>حساب شما مسدود شده است!</b>\n\nبا ادمین تماس بگیرید.",
                    parse_mode="HTML",
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ حساب شما مسدود شده است!", show_alert=True)
            return

        # دکمه بررسی عضویت باید بتواند خودش وضعیت عضویت را بررسی کند.
        if isinstance(event, CallbackQuery) and event.data == "check_join":
            return await handler(event, data)

        channels = await db.get_all_channels()
        if not channels:
            return await handler(event, data)

        bot = data["bot"]
        not_joined = []
        for channel in channels:
            try:
                member = await bot.get_chat_member(
                    chat_id=int(channel["channel_id"]),
                    user_id=user_id,
                )
                if member.status in {"left", "kicked"} or getattr(member, "is_member", True) is False:
                    not_joined.append(channel)
            except Exception:
                # اگر کانال موقتاً قابل بررسی نیست، کاربر را قفل نکنیم.
                continue

        if not_joined:
            text = (
                "⚠️ <b>برای استفاده از ربات باید در کانال‌های زیر عضو شوید:</b>\n\n"
                "پس از عضویت، دکمه «✅ بررسی عضویت» را بزنید."
            )
            keyboard = join_channels_keyboard(not_joined)
            if isinstance(event, Message):
                await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
            elif event.message:
                await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
                await event.answer(
                    "🔔 لطفاً ابتدا در کانال‌ها عضو شوید و سپس دکمه را فشار دهید.",
                    show_alert=True,
                )
            return

        return await handler(event, data)
