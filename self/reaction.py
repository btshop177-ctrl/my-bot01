"""
ماژول ری‌اکشن - ریکت خودکار روی کاربر، چت، کانال و متن خاص
نسخه اصلاح شده:
  - رفع باگ ریکت نزدن روی کاربر وقتی جوین گروه جدید میشه
  - مدیریت بهتر Flood و بازیابی خودکار
  - بهبود تشخیص sender_id
"""

import asyncio
import time
import re
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji


class ReactionManager:
    def __init__(self, client, config_manager):
        self.client = client
        self.config = config_manager
        self.last_react_time = 0
        self.min_delay = 1.0
        self._lock = asyncio.Lock()
        # ─── مدیریت Flood ───
        self._flood_until = 0
        self._consecutive_errors = 0
        self._max_consecutive = 5
        self._base_delay = 1.0
        self._current_delay = 1.0
        self._max_delay = 15.0

    async def _smart_rate_limit(self):
        """Rate limit هوشمند با بازیابی خودکار"""
        async with self._lock:
            now = time.time()

            if now < self._flood_until:
                wait = self._flood_until - now
                print(f"⏳ ریکت: صبر {wait:.1f}s (Flood)")
                await asyncio.sleep(wait)
                now = time.time()

            elapsed = now - self.last_react_time
            if elapsed < self._current_delay:
                await asyncio.sleep(self._current_delay - elapsed)

            self.last_react_time = time.time()

    def _on_success(self):
        """بعد از موفقیت، تاخیر رو کم کن"""
        self._consecutive_errors = 0
        if self._current_delay > self._base_delay:
            self._current_delay = max(
                self._base_delay,
                self._current_delay * 0.8
            )

    def _on_error(self, flood_seconds=0):
        """بعد از خطا، تاخیر رو زیاد کن"""
        self._consecutive_errors += 1

        if flood_seconds > 0:
            self._flood_until = time.time() + flood_seconds + 1
            self._current_delay = min(
                self._max_delay,
                self._current_delay * 2
            )
            print(
                f"⏳ Flood wait: {flood_seconds}s → "
                f"تاخیر جدید: {self._current_delay:.1f}s"
            )
        elif self._consecutive_errors >= self._max_consecutive:
            self._current_delay = min(
                self._max_delay,
                self._current_delay * 1.5
            )
            print(
                f"⚠️ خطاهای متوالی → "
                f"تاخیر جدید: {self._current_delay:.1f}s"
            )

    def _extract_flood_seconds(self, error_str):
        """استخراج ثانیه‌های Flood از پیام خطا"""
        match = re.search(
            r'(\d+)\s*(?:seconds?|s)', error_str, re.IGNORECASE
        )
        if match:
            return int(match.group(1))
        if "FLOOD" in error_str.upper():
            return 10
        return 0

    async def _send_auto_react(self, chat_id, msg_id, emoji, source):
        """ارسال ریکت خودکار با مدیریت خطای پیشرفته"""
        try:
            await self._smart_rate_limit()
            await self.client(SendReactionRequest(
                peer=chat_id,
                msg_id=msg_id,
                reaction=[ReactionEmoji(emoticon=emoji)]
            ))
            self._on_success()
            print(f"💜 Auto React [{source}]: {emoji}")
            return True

        except Exception as e:
            error = str(e)
            error_upper = error.upper()

            if "FLOOD" in error_upper or "WAIT" in error_upper:
                seconds = self._extract_flood_seconds(error)
                self._on_error(flood_seconds=seconds)
                return False

            elif "REACTION_INVALID" in error_upper:
                print(f"⚠️ ایموجی {emoji} در {chat_id} مجاز نیست")
                return False

            elif "MSG_ID_INVALID" in error_upper:
                return False

            elif "CHAT_WRITE_FORBIDDEN" in error_upper:
                print(f"⚠️ اجازه ریکت در {chat_id} ندارید")
                return False

            elif "PEER_ID_INVALID" in error_upper:
                print(f"⚠️ چت {chat_id} نامعتبر")
                return False

            else:
                self._on_error()
                print(f"⚠️ خطای ریکت [{source}]: {error[:80]}")
                return False

    async def send_reaction(self, chat_id, msg_id, emoji):
        try:
            await self._smart_rate_limit()
            await self.client(SendReactionRequest(
                peer=chat_id,
                msg_id=msg_id,
                reaction=[ReactionEmoji(emoticon=emoji)]
            ))
            self._on_success()
            return True, f"✅ ریکشن {emoji} ارسال شد"
        except Exception as e:
            error_msg = str(e)
            if "REACTION_INVALID" in error_msg:
                return False, f"❌ ایموجی {emoji} در این چت مجاز نیست"
            elif "MSG_ID_INVALID" in error_msg:
                return False, "❌ پیام پیدا نشد"
            elif "PEER_ID_INVALID" in error_msg:
                return False, "❌ چت پیدا نشد"
            elif "CHAT_WRITE_FORBIDDEN" in error_msg:
                return False, "❌ اجازه ریکت ندارید"
            elif "FLOOD" in error_msg.upper():
                seconds = self._extract_flood_seconds(error_msg)
                self._on_error(flood_seconds=seconds)
                return False, f"⏳ محدودیت تلگرام ({seconds}s)"
            else:
                self._on_error()
                return False, f"❌ خطا: {error_msg[:80]}"

    async def remove_reaction(self, chat_id, msg_id):
        try:
            await self._smart_rate_limit()
            await self.client(SendReactionRequest(
                peer=chat_id,
                msg_id=msg_id,
                reaction=[]
            ))
            return True, "✅ ریکشن حذف شد"
        except Exception as e:
            return False, f"❌ خطا: {str(e)[:80]}"

    # ═══════════════════════════════════════
    # افزودن ریکت کاربر
    # ═══════════════════════════════════════
    def add_user_react(self, user_id, emoji, user_name=""):
        users = self.config.get("user_reactions", [])
        for u in users:
            if u["user_id"] == user_id:
                u["emoji"] = emoji
                u["user_name"] = user_name
                self.config.save()
                return f"✅ ریکت **{user_name}** بروزرسانی شد → {emoji}"

        users.append({
            "user_id": user_id,
            "emoji": emoji,
            "user_name": user_name,
            "enabled": True
        })
        self.config.set("user_reactions", users)
        return (
            f"✅ **ریکت خودکار روی کاربر فعال شد**\n\n"
            f"👤 کاربر: **{user_name}**\n"
            f"🆔 آیدی: `{user_id}`\n"
            f"❤️ ایموجی: {emoji}"
        )

    # ═══════════════════════════════════════
    # افزودن ریکت چت / کانال
    # ═══════════════════════════════════════
    def add_chat_react(self, chat_id, emoji, chat_name=""):
        chats = self.config.get("chat_reactions", [])
        for c in chats:
            if c["chat_id"] == chat_id:
                c["emoji"] = emoji
                c["chat_name"] = chat_name
                self.config.save()
                return (
                    f"✅ ریکت چت **{chat_name}** بروزرسانی شد → {emoji}"
                )

        chats.append({
            "chat_id": chat_id,
            "emoji": emoji,
            "chat_name": chat_name,
            "enabled": True
        })
        self.config.set("chat_reactions", chats)
        return (
            f"✅ **ریکت خودکار روی چت/کانال فعال شد**\n\n"
            f"💬 چت: **{chat_name}**\n"
            f"🆔 آیدی: `{chat_id}`\n"
            f"❤️ ایموجی: {emoji}"
        )

    # ═══════════════════════════════════════
    # افزودن ریکت بر اساس متن خاص
    # ═══════════════════════════════════════
    def add_text_react(self, keyword, emoji):
        text_reacts = self.config.get("text_reactions", [])
        for t in text_reacts:
            if t["keyword"] == keyword:
                t["emoji"] = emoji
                self.config.save()
                return (
                    f"✅ ریکت متن **{keyword}** بروزرسانی شد → {emoji}"
                )

        text_reacts.append({
            "keyword": keyword,
            "emoji": emoji,
            "enabled": True
        })
        self.config.set("text_reactions", text_reacts)
        return (
            f"✅ **ریکت بر اساس متن فعال شد**\n\n"
            f"📝 کلمه: **{keyword}**\n"
            f"❤️ ایموجی: {emoji}"
        )

    def remove_text_react(self, keyword):
        text_reacts = self.config.get("text_reactions", [])
        new_list = [t for t in text_reacts if t["keyword"] != keyword]
        if len(new_list) == len(text_reacts):
            return f"❌ کلمه `{keyword}` در لیست ریکت متنی نیست"
        self.config.set("text_reactions", new_list)
        return f"✅ ریکت متن **{keyword}** حذف شد"

    # ═══════════════════════════════════════
    # حذف
    # ═══════════════════════════════════════
    def remove_by_index(self, index):
        users = self.config.get("user_reactions", [])
        chats = self.config.get("chat_reactions", [])
        texts = self.config.get("text_reactions", [])

        total = len(users) + len(chats) + len(texts)
        if index < 1 or index > total:
            return f"❌ شماره نامعتبر! (بین 1 تا {total})"

        if index <= len(users):
            removed = users.pop(index - 1)
            self.config.set("user_reactions", users)
            name = removed.get("user_name") or str(removed["user_id"])
            return f"✅ ریکت کاربر **{name}** حذف شد"
        elif index <= len(users) + len(chats):
            chat_index = index - len(users) - 1
            removed = chats.pop(chat_index)
            self.config.set("chat_reactions", chats)
            name = removed.get("chat_name") or str(removed["chat_id"])
            return f"✅ ریکت چت **{name}** حذف شد"
        else:
            text_index = index - len(users) - len(chats) - 1
            removed = texts.pop(text_index)
            self.config.set("text_reactions", texts)
            return f"✅ ریکت متن **{removed['keyword']}** حذف شد"

    def remove_by_id(self, target_id):
        users = self.config.get("user_reactions", [])
        chats = self.config.get("chat_reactions", [])

        for u in users:
            if u["user_id"] == target_id:
                users.remove(u)
                self.config.set("user_reactions", users)
                name = u.get("user_name") or str(target_id)
                return f"✅ ریکت کاربر **{name}** حذف شد"

        for c in chats:
            if c["chat_id"] == target_id:
                chats.remove(c)
                self.config.set("chat_reactions", chats)
                name = c.get("chat_name") or str(target_id)
                return f"✅ ریکت چت **{name}** حذف شد"

        return f"❌ آیدی `{target_id}` در لیست ریکت‌ها نیست"

    def clear_all(self):
        self.config.set("user_reactions", [])
        self.config.set("chat_reactions", [])
        self.config.set("text_reactions", [])
        return "🗑 تمام ریکت‌های خودکار پاک شدند"

    def get_full_list(self) -> str:
        users = self.config.get("user_reactions", [])
        chats = self.config.get("chat_reactions", [])
        texts = self.config.get("text_reactions", [])

        if not users and not chats and not texts:
            return "📭 **لیست ریکت خودکار خالی است**"

        text = "📋 **لیست ریکت‌های خودکار:**\n\n"
        counter = 1

        if users:
            text += "👤 **کاربران:**\n"
            for u in users:
                name = u.get("user_name") or str(u["user_id"])
                status = "🟢" if u.get("enabled", True) else "🔴"
                text += (
                    f"  {status} `{counter}` ▸ {name} → {u['emoji']}\n"
                )
                text += f"       آیدی: `{u['user_id']}`\n"
                counter += 1
            text += "\n"

        if chats:
            text += "💬 **چت‌ها/کانال‌ها:**\n"
            for c in chats:
                name = c.get("chat_name") or str(c["chat_id"])
                status = "🟢" if c.get("enabled", True) else "🔴"
                text += (
                    f"  {status} `{counter}` ▸ {name} → {c['emoji']}\n"
                )
                text += f"       آیدی: `{c['chat_id']}`\n"
                counter += 1
            text += "\n"

        if texts:
            text += "📝 **متن‌های خاص:**\n"
            for t in texts:
                status = "🟢" if t.get("enabled", True) else "🔴"
                text += (
                    f"  {status} `{counter}` ▸ "
                    f"\"{t['keyword']}\" → {t['emoji']}\n"
                )
                counter += 1
            text += "\n"

        text += (
            f"**دستورات حذف:**\n"
            f"`حذف ریکت [شماره]`\n"
            f"`حذف ریکت [آیدی]`\n"
            f"`حذف ریکت متن [کلمه]`\n"
            f"`پاکسازی ریکت`"
        )
        return text

    # ═══════════════════════════════════════
    # استخراج sender_id واقعی
    # ═══════════════════════════════════════
    async def _get_real_sender_id(self, event):
        """
        استخراج sender_id واقعی از پیام
        حتی اگه از کانال فوروارد شده یا ناشناس باشه
        """
        # روش ۱: مستقیم
        sender_id = event.sender_id
        if sender_id:
            return sender_id

        # روش ۲: از message.from_id
        try:
            msg = event.message
            if msg and msg.from_id:
                from telethon.tl.types import PeerUser, PeerChannel
                if isinstance(msg.from_id, PeerUser):
                    return msg.from_id.user_id
                elif isinstance(msg.from_id, PeerChannel):
                    return msg.from_id.channel_id
        except Exception:
            pass

        # روش ۳: از peer_id (پیام کانال)
        try:
            if hasattr(event, 'peer_id'):
                from telethon.tl.types import PeerChannel
                if isinstance(event.peer_id, PeerChannel):
                    return event.peer_id.channel_id
        except Exception:
            pass

        return None

    # ═══════════════════════════════════════
    # هندلر پیام‌های ورودی (اصلاح شده)
    # ═══════════════════════════════════════
    async def handle_new_message(self, event):
        """
        هندلر اصلی - بررسی همه پیام‌های ورودی
        اصلاح‌شده: جلوگیری از ارسال چند درخواست همزمان برای یک پیام در صورت خطا
        """
        chat_id = event.chat_id
        msg_text = event.raw_text or ""

        # استخراج sender_id واقعی
        sender_id = await self._get_real_sender_id(event)

        reacted = False

        # ─── چک ریکت کاربر (اولویت اول) ───
        if sender_id and not reacted:
            users = self.config.get("user_reactions", [])
            for u in users:
                if u["user_id"] == sender_id and u.get("enabled", True):
                    reacted = True  # مارک کردن به عنوان پردازش شده
                    await self._send_auto_react(
                        chat_id, event.id, u["emoji"],
                        f"user:{sender_id}"
                    )
                    break

        # ─── چک ریکت چت/کانال (اولویت دوم) ───
        if not reacted:
            chats = self.config.get("chat_reactions", [])
            for c in chats:
                if c["chat_id"] == chat_id and c.get("enabled", True):
                    reacted = True  # مارک کردن به عنوان پردازش شده
                    await self._send_auto_react(
                        chat_id, event.id, c["emoji"],
                        f"chat:{chat_id}"
                    )
                    break

        # ─── چک ریکت متن خاص (اولویت سوم) ───
        if not reacted and msg_text:
            text_reacts = self.config.get("text_reactions", [])
            msg_words = msg_text.split()
            for t in text_reacts:
                if t.get("enabled", True):
                    keyword = t["keyword"]
                    if (keyword == msg_text
                            or keyword in msg_words
                            or keyword.lower() in msg_text.lower()):
                        reacted = True  # مارک کردن به عنوان پردازش شده
                        await self._send_auto_react(
                            chat_id, event.id, t["emoji"],
                            f"text:{keyword}"
                        )
                        break