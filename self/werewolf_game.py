"""ردیابی بازی گرگینه، برآورد وضعیت روستا و رأی خودکار.

این ماژول فقط پیام‌های ربات رسمی با شناسهٔ ثابت WEREWOLF_BOT_ID را می‌پذیرد.
رأی‌ها به شکل صف نگهداری می‌شوند؛ رأی دوم دردسرساز هرگز رأی دور بعد را
مصرف نمی‌کند.
"""

import asyncio
import re
from collections import deque


WEREWOLF_BOT_ID = 175844556
START_TEXT = "ایول بازی شروع شد 😃 یه کم صبر کنین نقشاتونو بهتون بگم"
ASK_LYNCH_PARTS = ("به کی رای میدی که اعدام بشه", "کیو میخواین اعدام کنین")
CHOICE_ACCEPTED = "انتخاب پذیرفته شد"
TIMES_UP = "وقت تموم شد"
PLAYER_LIST_RE = re.compile(r"#players\s*:\s*(\d+)", re.IGNORECASE)
END_GAME_RE = re.compile(r"مدت\s*زمان\s*بازی\s*:")
CALLBACK_TARGET_RE = re.compile(rb"\|(-?\d+)$")


def _compact(text):
    return " ".join((text or "").replace("ي", "ی").replace("ك", "ک").split())


def _target_record(target_id, name=""):
    return {"id": int(target_id), "name": (name or str(target_id)).strip()}


class WerewolfGameManager:
    def __init__(self, client, config_manager, owner_id=None):
        self.client = client
        self.config = config_manager
        self.owner_id = owner_id
        self.game_active = False
        self.group_id = None
        self.player_count = 0
        self.game_mode = "unknown"
        self.known_modes = {}

        self.normal_votes = deque()
        self.trouble_vote = None
        self.next_prompt_is_trouble = False
        self.waiting_trouble_prompt = None
        self.current_attempt = None
        self.vote_lock = asyncio.Lock()
        self.next_join_lock = asyncio.Lock()
        self.next_join_task = None
        self.next_group_id = self.config.get("werewolf_next_group_id")
        self._load_votes()

    # ─────────────────────────────────────────
    # تنظیمات و صف رأی
    # ─────────────────────────────────────────

    def is_vote_enabled(self):
        return bool(self.config.get("werewolf_vote_enabled", False))

    def enable_votes(self):
        self.config.set("werewolf_vote_enabled", True)
        return "✅ رأی خودکار گرگینه روشن شد."

    def disable_votes(self):
        self.config.set("werewolf_vote_enabled", False)
        self.clear_votes()
        return "🔴 رأی خودکار خاموش شد و همهٔ رأی‌های ثبت‌شده پاک شدند."

    def _load_votes(self):
        saved = self.config.get("werewolf_votes", [])
        for vote in saved if isinstance(saved, list) else []:
            try:
                self.normal_votes.append(_target_record(vote["id"], vote.get("name", "")))
            except (KeyError, TypeError, ValueError):
                continue

    def _save_votes(self):
        self.config.set("werewolf_votes", list(self.normal_votes))

    def clear_votes(self):
        self.normal_votes.clear()
        self.trouble_vote = None
        self.waiting_trouble_prompt = None
        self.current_attempt = None
        self.next_prompt_is_trouble = False
        self._save_votes()

    def reset_game(self, group_id=None):
        self.clear_votes()
        self.game_active = group_id is not None
        self.group_id = group_id
        self.player_count = 0
        self.game_mode = self.known_modes.get(group_id, "unknown")

    async def register_vote(self, target_id, name=""):
        vote = _target_record(target_id, name)

        # وقتی منوی رأی دوم دردسر باز است، رأی تازه مخصوص همان منو است و
        # وارد صف دورهای عادی نمی‌شود.
        if self.waiting_trouble_prompt is not None:
            self.trouble_vote = vote
            message = self.waiting_trouble_prompt
            self.waiting_trouble_prompt = None
            success, detail = await self._click_vote(message, vote)
            self.trouble_vote = None
            if success:
                return f"✅ رأی دوم دردسر ثبت شد: {vote['name']}"
            return f"❌ رأی دوم ثبت نشد: {detail}"

        self.normal_votes.append(vote)
        self._save_votes()
        position = len(self.normal_votes)
        return f"✅ رأی {vote['name']} برای دور عادی شمارهٔ {position} ذخیره شد."

    def get_vote_panel_text(self):
        status = "🟢 روشن" if self.is_vote_enabled() else "🔴 خاموش"
        lines = [
            "🗳 رأی خودکار گرگینه",
            "",
            f"وضعیت: {status}",
            f"رأی‌های دورهای آینده: {len(self.normal_votes)}",
        ]
        if self.normal_votes:
            lines.append("")
            lines.append("صف فعلی:")
            for index, vote in enumerate(self.normal_votes, 1):
                lines.append(f"{index}. {vote['name']} ({vote['id']})")
        lines.extend((
            "",
            "ثبت رأی:",
            "رای 123456789",
            "رای @username",
            "رای + ریپلای روی پیام شخص",
            "",
            "رأی دوم دردسر از صف شب‌های بعد مصرف نمی‌شود.",
        ))
        return "\n".join(lines)

    # ─────────────────────────────────────────
    # انتظار بازی بعدی و جوین خودکار
    # ─────────────────────────────────────────

    def set_next_wait(self, group_id):
        self.next_group_id = int(group_id)
        self.config.set("werewolf_next_group_id", self.next_group_id)

    def clear_next_wait(self):
        self.next_group_id = None
        self.config.set("werewolf_next_group_id", None)

    async def cancel_next_wait(self, group_id=None):
        """دکمهٔ کنسل مربوط به /nextgame را در خصوصی ربات می‌زند."""
        wanted_group = group_id or self.next_group_id
        try:
            messages = await self.client.get_messages(WEREWOLF_BOT_ID, limit=50)
            for message in messages:
                for row in message.buttons or []:
                    for button in row:
                        data = getattr(button, "data", b"") or b""
                        if not data.startswith(b"stopwaiting|"):
                            continue
                        try:
                            button_group = int(data.decode().split("|", 1)[1])
                        except (ValueError, IndexError, UnicodeDecodeError):
                            continue
                        if wanted_group and button_group != int(wanted_group):
                            continue
                        answer = await message.click(data=data)
                        self.clear_next_wait()
                        return True, _compact(getattr(answer, "message", "")) or "از لیست انتظار خارج شدید"
        except Exception as exc:
            return False, str(exc)[:120]
        return False, "دکمهٔ کنسل لیست انتظار پیدا نشد"

    def _is_next_notification(self, text):
        return "هورا یه بازی جدید توی گروه" in text and "شروع شده" in text

    async def _schedule_auto_join(self, notification):
        if self.next_join_task and not self.next_join_task.done():
            return
        self.next_join_task = asyncio.create_task(self._auto_join_next_game(notification))

    async def _auto_join_next_game(self, notification):
        """پیام شروع بازی را در گروه پیدا و دیپ‌لینک Join را اجرا می‌کند."""
        async with self.next_join_lock:
            group = None
            if self.next_group_id:
                try:
                    group = await self.client.get_entity(int(self.next_group_id))
                except Exception:
                    group = None

            if group is None:
                group = await self._group_from_notification(notification)
            if group is None:
                await self.client.send_message(
                    "me", "❌ نکست: گروه بازی از پیام ربات تشخیص داده نشد."
                )
                return

            # پیام گروه ممکن است چند لحظه بعد از اعلان خصوصی برسد.
            for _ in range(6):
                try:
                    messages = await self.client.get_messages(group, limit=30)
                    for message in messages:
                        if getattr(message, "sender_id", None) != WEREWOLF_BOT_ID:
                            continue
                        for row in message.buttons or []:
                            for button in row:
                                url = getattr(button, "url", "") or ""
                                match = re.search(
                                    r"(?:https?://)?t\.me/(?:werewolfbot)/?\?start=(join[^&\s]+)",
                                    url, re.IGNORECASE
                                )
                                if not match:
                                    continue
                                payload = match.group(1)
                                await self.client.send_message(
                                    WEREWOLF_BOT_ID, f"/start {payload}"
                                )
                                self.clear_next_wait()
                                await self.client.send_message(
                                    "me", "✅ نکست: دکمهٔ ورود بازی جدید خودکار اجرا شد."
                                )
                                return
                except Exception as exc:
                    last_error = str(exc)[:120]
                else:
                    last_error = "دکمهٔ ورود هنوز در گروه دیده نشد"
                await asyncio.sleep(2)

            await self.client.send_message(
                "me", f"❌ نکست: ورود خودکار انجام نشد؛ {last_error}"
            )

    async def _group_from_notification(self, message):
        """گروه لینک‌شده در اعلان خصوصی را بدون وابستگی به متن نمایشی می‌یابد."""
        urls = []
        for entity in getattr(message, "entities", None) or []:
            url = getattr(entity, "url", None)
            if url:
                urls.append(url)
        for url in urls:
            try:
                public = re.search(r"t\.me/([A-Za-z][A-Za-z0-9_]{3,})", url)
                if public and public.group(1).lower() not in ("joinchat", "werewolfbot"):
                    return await self.client.get_entity(public.group(1))

                invite = re.search(r"t\.me/(?:joinchat/|\+)([A-Za-z0-9_-]+)", url)
                if invite:
                    from telethon.tl.functions.messages import CheckChatInviteRequest
                    checked = await self.client(CheckChatInviteRequest(invite.group(1)))
                    chat = getattr(checked, "chat", None)
                    if chat:
                        return chat
            except Exception:
                continue
        return None

    def _owner_is_dead_in_list(self, message, text):
        if (not self.owner_id
                or ("بازیکن های زنده" not in text
                    and "بازیکن‌های زنده" not in text)):
            return False
        try:
            from telethon.helpers import add_surrogate
            from telethon.tl.types import MessageEntityMentionName, MessageEntityTextUrl
            surrogate = add_surrogate(message.raw_text or "")
            for entity in message.entities or []:
                is_owner = False
                if isinstance(entity, MessageEntityMentionName):
                    is_owner = entity.user_id == self.owner_id
                elif isinstance(entity, MessageEntityTextUrl):
                    is_owner = f"user?id={self.owner_id}" in (entity.url or "")
                if not is_owner:
                    continue
                start = surrogate.rfind("\n", 0, entity.offset) + 1
                end = surrogate.find("\n", entity.offset + entity.length)
                if end < 0:
                    end = len(surrogate)
                line = surrogate[start:end]
                if "مرده" in line:
                    return True
        except Exception:
            return False
        return False

    # ─────────────────────────────────────────
    # تشخیص وضعیت بازی از پیام‌های گروه
    # ─────────────────────────────────────────

    async def handle_bot_message(self, event, edited=False):
        if event.sender_id != WEREWOLF_BOT_ID:
            return

        text = _compact(event.raw_text)
        if not text:
            return

        if event.is_private and self._is_next_notification(text):
            await self._schedule_auto_join(event.message)
            return

        # پیام ساخت بازی پیش از شروع، مود را مشخص می‌کند.
        if "یک بازی با حالت آشوب" in text:
            self.known_modes[event.chat_id] = "chaos"
        elif "یک بازی توسط" in text and "ساخته شده" in text:
            self.known_modes[event.chat_id] = "normal"

        if "چقدر کمین! من با این تعداد بازیکن بازی رو شروع نمیکنم" in text:
            self.known_modes.pop(event.chat_id, None)
            self.reset_game()
            return

        if _compact(START_TEXT) in text:
            self.reset_game(event.chat_id)
            return

        if self.game_active and event.chat_id == self.group_id:
            match = PLAYER_LIST_RE.search(text)
            if match:
                self.player_count = int(match.group(1))

            if self._owner_is_dead_in_list(event.message, text):
                self.clear_votes()

            if "بخاطر مشکلات ایجاد شده شما امروز دوبار رای گیری میکنید" in text or \
                    "بخاطر مشکلات ایجاد شده شما امروز دو بار رای گیری میکنید" in text:
                self.next_prompt_is_trouble = True

            if "امروز رای گیری نداریم" in text or "امروز رای‌گیری نداریم" in text:
                await self._handle_peace()

            if (END_GAME_RE.search(text)
                    and ("بازیکن های زنده" in text
                         or "بازیکن‌های زنده" in text)):
                self.game_active = False
                self.group_id = None
                self.player_count = 0
                self.clear_votes()
                return

        # پیام خصوصی منوی اعدام یا ویرایش آن توسط ربات.
        if event.is_private:
            if any(part in text for part in ASK_LYNCH_PARTS) and event.message.buttons:
                await self._handle_lynch_prompt(event.message)
            elif "امروز رای گیری نداریم" in text or "امروز رای‌گیری نداریم" in text:
                await self._handle_peace()
            elif TIMES_UP in text:
                self.current_attempt = None
                self.waiting_trouble_prompt = None

    async def _handle_lynch_prompt(self, message):
        if not self.is_vote_enabled() or not self.game_active:
            return

        is_trouble = self.next_prompt_is_trouble
        self.next_prompt_is_trouble = False

        if is_trouble:
            if self.trouble_vote:
                vote = self.trouble_vote
                self.trouble_vote = None
                await self._click_vote(message, vote)
                return

            self.waiting_trouble_prompt = message
            await self.client.send_message(
                "me",
                "🤯 رأی اول شما ثبت شد و دردسر فعال است.\n"
                "اگر برای رأی دوم کسی را انتخاب می‌کنید، همین حالا بنویسید:\n"
                "رای آیدی عددی | رای @username | رای با ریپلای\n\n"
                "رأی‌های صف دورهای بعد برای دردسر مصرف نمی‌شوند."
            )
            return

        if not self.normal_votes:
            await self.client.send_message(
                "me", "🗳 منوی رأی گرگینه آمد، اما رأی ذخیره‌شده‌ای ندارید."
            )
            return

        vote = self.normal_votes.popleft()
        self._save_votes()
        self.current_attempt = {"kind": "normal", "vote": vote}
        success, detail = await self._click_vote(message, vote)
        if success:
            # تا پایان مهلت نگه می‌داریم تا اگر صلح‌گرا رأی‌گیری را لغو کرد،
            # رأی به ابتدای صف دور بعد برگردد.
            self.current_attempt["accepted"] = True
        else:
            self.normal_votes.appendleft(vote)
            self._save_votes()
            self.current_attempt = None
            await self.client.send_message(
                "me", f"❌ رأی خودکار به {vote['name']} ثبت نشد: {detail}"
            )

    async def _handle_peace(self):
        # رأی عادیِ مصرف‌شده در رأی‌گیری لغوشده باید برای دور بعد حفظ شود.
        if self.current_attempt and self.current_attempt.get("kind") == "normal":
            vote = self.current_attempt["vote"]
            if not self.normal_votes or self.normal_votes[0]["id"] != vote["id"]:
                self.normal_votes.appendleft(vote)
                self._save_votes()
        self.current_attempt = None
        self.waiting_trouble_prompt = None
        self.trouble_vote = None
        self.next_prompt_is_trouble = False

    # ─────────────────────────────────────────
    # کلیک امن روی دکمهٔ بازیکن
    # ─────────────────────────────────────────

    def _find_button(self, message, target_id):
        for row in message.buttons or []:
            for button in row:
                data = getattr(button, "data", None)
                if not data:
                    continue
                match = CALLBACK_TARGET_RE.search(data)
                if match and int(match.group(1)) == int(target_id):
                    return button
        return None

    async def _click_vote(self, message, vote):
        async with self.vote_lock:
            button = self._find_button(message, vote["id"])
            if button is None:
                return False, "بازیکن در فهرست افراد زنده پیدا نشد"

            last_error = "پاسخ تأیید دریافت نشد"
            for attempt in range(2):
                if attempt:
                    await asyncio.sleep(3)
                try:
                    answer = await message.click(data=button.data)
                    answer_text = _compact(getattr(answer, "message", ""))
                    if CHOICE_ACCEPTED in answer_text:
                        await self.client.send_message(
                            "me", f"✅ رأی گرگینه ثبت شد: {vote['name']}"
                        )
                        return True, answer_text
                    if TIMES_UP in answer_text:
                        return False, "وقت رأی‌گیری تمام شد"
                    if answer_text:
                        last_error = answer_text
                except Exception as exc:
                    last_error = str(exc)[:120]
            return False, last_error

    # ─────────────────────────────────────────
    # وضعیت روستا
    # ─────────────────────────────────────────

    def get_village_status(self):
        if not self.game_active or not self.player_count:
            return "❌ هنوز بازی فعال و فهرست بازیکنان شناسایی نشده است."

        count = self.player_count
        wolves = min(max(count // 5, 1), 5)
        max_negative = (count - 1) // 2
        min_village = count - max_negative
        max_village = count - wolves
        mode = {"normal": "معمولی", "chaos": "آشوب", "unknown": "نامشخص"}[self.game_mode]

        return (
            "🐺 **وضعیت احتمالی روستا**\n\n"
            f"🎮 مود شناسایی‌شده: {mode}\n"
            f"👥 تعداد بازیکنان: {count}\n"
            f"🐺 گرگ‌های اولیه: حدود {wolves}\n"
            f"🔴 کل نقش‌های منفی/مستقل: بین {wolves} تا {max_negative}\n"
            f"🟢 نقش‌های روستایی: بین {min_village} تا {max_village}\n\n"
            "این اعداد بازهٔ احتمالی‌اند؛ ترکیب دقیق مخفی است و تنظیمات گروه، "
            "تبدیل نفرین‌شده، بچهٔ وحشی، خائن و فرقه می‌تواند وضعیت را تغییر دهد."
        )
