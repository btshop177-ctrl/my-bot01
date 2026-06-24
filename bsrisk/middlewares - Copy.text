from typing import Callable, Dict, Any, Awaitable, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from database import db
from keyboards import join_channels_keyboard
from config import ADMIN_IDS


class JoinCheckMiddleware(BaseMiddleware):
    """میدلور بررسی عضویت + بن + فقط PV"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        if not hasattr(event, 'from_user') or event.from_user is None:
            return await handler(event, data)

        # ربات‌ها رو رد کن
        if event.from_user.is_bot:
            return await handler(event, data)

        user_id = event.from_user.id

        # ═══ بررسی گروه/کانال ═══
        if isinstance(event, Message):
            chat_type = event.chat.type
            # در کانال هیچ کاری نکن
            if chat_type == "channel":
                return

            # در گروه/سوپرگروه → فقط جوین اجباری چک شه
            if chat_type in ["group", "supergroup"]:
                # ادمین‌ها آزاد هستن
                if user_id in ADMIN_IDS:
                    return await handler(event, data)
                # بقیه پیام‌ها رو به هندلر گروه بفرست
                return await handler(event, data)

        # ═══ فقط PV از اینجا به بعد ═══

        # ادمین‌ها بدون محدودیت
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        # بررسی بن
        user_data = await db.get_user(user_id)
        if user_data and user_data['is_banned']:
            if isinstance(event, Message):
                await event.answer("⛔ <b>حساب شما مسدود شده است!</b>\n\nبا ادمین تماس بگیرید.",
                                   parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ حساب شما مسدود شده است!", show_alert=True)
            return

        # اگر callback بررسی عضویت است، اجازه بده
        if isinstance(event, CallbackQuery) and event.data == "check_join":
            return await handler(event, data)

        # بررسی عضویت کانال‌ها
        channels = await db.get_all_channels()
        if not channels:
            return await handler(event, data)

        bot = data["bot"]
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

        if not_joined:
            text = (
                "⚠️ <b>برای استفاده از ربات باید در کانال‌های زیر عضو شوید:</b>\n\n"
                "پس از عضویت، دکمه «✅ بررسی عضویت» را بزنید."
            )
            keyboard = join_channels_keyboard(not_joined)

            if isinstance(event, Message):
                await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
                await event.answer(
                    "🔔 لطفاً ابتدا در کانال‌ها عضو شوید و سپس\n"
                    "دکمه را فشار دهید!\n\n"
                    "❗ اگر عضو شدید و هنوز این پیام را\n"
                    "مشاهده میکنید , با ادمین تماس بگیرید!",
                    show_alert=True
                )
            return

        return await handler(event, data)