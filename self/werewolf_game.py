"""ردیابی چند بازی گرگینه، وضعیت روستا و رأی خودکار.

فقط پیام‌های ربات رسمی Werewolf پردازش می‌شوند. هر گروه وضعیت و صف رأی
مستقل دارد و منوی خصوصی رأی از روی شناسهٔ بازی داخل callback به گروه درست
وصل می‌شود.
"""

import asyncio
import re
from collections import deque


WEREWOLF_BOT_ID = 175844556
START_TEXT = "ایول بازی شروع شد 😃 یه کم صبر کنین نقشاتونو بهتون بگم"
NOT_ENOUGH_TEXT = "چقدر کمین! من با این تعداد بازیکن بازی رو شروع نمیکنم"
ASK_LYNCH_PARTS = ("به کی رای میدی که اعدام بشه", "کیو میخواین اعدام کنین")
CHOICE_ACCEPTED = "انتخاب پذیرفته شد"
TIMES_UP = "وقت تموم شد"
PLAYER_LIST_RE = re.compile(r"#players\s*:\s*(\d+)", re.IGNORECASE)
ALIVE_LIST_RE = re.compile(r"بازیکن[‌ ]های زنده\s*:\s*(\d+)\s*/\s*(\d+)")
END_GAME_RE = re.compile(r"مدت\s*زمان\s*بازی\s*:")
CALLBACK_TARGET_RE = re.compile(rb"\|(-?\d+)$")
START_COMMAND_RE = re.compile(
    r"^/(startchaos|startgame)(?:@werewolfbot)?$", re.IGNORECASE
)
VALID_TARGET_RE = re.compile(r"^(?:@?[A-Za-z0-9_]{3,}|\d{5,})$")


def _compact(text):
    return " ".join((text or "").replace("ي", "ی").replace("ك", "ک").split())


def _target_record(target_id, name=""):
    return {"id": int(target_id), "name": (name or str(target_id)).strip()}


def is_vote_registration(text, is_reply=False):
    """فقط «رای» ریپلای‌شده یا «رای شناسه» را دستور حساب می‌کند."""
    text = (text or "").strip()
    if is_reply:
        return text == "رای"
    if not text.startswith("رای "):
        return False
    target = text[4:].strip()
    return bool(VALID_TARGET_RE.fullmatch(target))


def parse_vote_index_command(text, prefix):
    text = (text or "").strip()
    if not text.startswith(prefix + " "):
        return None
    rest = text[len(prefix):].strip()
    first = rest.split(maxsplit=1)[0] if rest else ""
    return int(first) if first.isdigit() and int(first) > 0 else None


class WerewolfGameManager:
    def __init__(self, client, config_manager, owner_id=None,
                 owner_names=None):
        self.client = client
        self.config = config_manager
        self.owner_id = owner_id
        self.owner_names = {
            _compact(name).lower() for name in (owner_names or []) if name
        }
        self.games = {}
        self.vote_lock = asyncio.Lock()
        self.next_join_lock = asyncio.Lock()
        self.next_join_tasks = {}
        self.next_group_ids = set(
            int(x) for x in self.config.get("werewolf_next_group_ids", [])
            if str(x).lstrip("-").isdigit()
        )
        legacy_next = self.config.get("werewolf_next_group_id")
        if legacy_next:
            self.next_group_ids.add(int(legacy_next))
        self._load_games()

    # ─────────────────────────────────────────
    # وضعیت بازی‌های گروهی
    # ─────────────────────────────────────────

    def _new_state(self, group_id, mode="unknown", manual=False):
        return {
            "group_id": int(group_id),
            "mode": mode,
            "manual": manual,
            "owner_joined": manual,
            "started": False,
            "player_count": 0,
            "alive_count": 0,
            "join_token": None,
            "normal_votes": deque(),
            "trouble_vote": None,
            "next_prompt_is_trouble": False,
            "waiting_trouble_prompt": None,
            "current_attempt": None,
        }

    def _state(self, group_id, create=False, mode="unknown", manual=False):
        if group_id is None:
            return None
        group_id = int(group_id)
        state = self.games.get(group_id)
        if state is None and create:
            state = self._new_state(group_id, mode, manual)
            self.games[group_id] = state
        elif state and mode != "unknown":
            state["mode"] = mode
        if state and manual:
            state["manual"] = True
            state["owner_joined"] = True
        return state

    def track_group_manually(self, group_id):
        self._state(group_id, create=True, manual=True)
        self._save_games()
        try:
            asyncio.create_task(self._scan_recent_group(group_id))
        except RuntimeError:
            pass
        return "✅ این گروه برای بازی گرگینه ثبت شد و پیام‌های اخیر بررسی می‌شوند."

    def untrack_group(self, group_id):
        state = self.games.pop(int(group_id), None)
        self._save_games()
        if state:
            return "✅ این گروه از بازی‌های گرگینه حذف شد."
        return "❌ این گروه در فهرست بازی‌های گرگینه نبود."

    def is_tracked_group(self, group_id):
        state = self._state(group_id)
        return bool(state and state["owner_joined"])

    def _clear_state_votes(self, state):
        state["normal_votes"].clear()
        state["trouble_vote"] = None
        state["next_prompt_is_trouble"] = False
        state["waiting_trouble_prompt"] = None
        state["current_attempt"] = None

    def reset_group(self, group_id, remove=False):
        state = self._state(group_id)
        if not state:
            return
        self._clear_state_votes(state)
        if remove and not state["manual"]:
            self.games.pop(int(group_id), None)
        else:
            state["started"] = False
            state["player_count"] = 0
            state["alive_count"] = 0
            state["join_token"] = None
            if not state["manual"]:
                state["owner_joined"] = False
        self._save_games()

    # ─────────────────────────────────────────
    # تنظیم و نگهداری صف رأی هر گروه
    # ─────────────────────────────────────────

    def is_vote_enabled(self):
        return bool(self.config.get("werewolf_vote_enabled", False))

    def enable_votes(self):
        self.config.set("werewolf_vote_enabled", True)
        return "✅ رأی خودکار گرگینه روشن شد."

    def disable_votes(self):
        self.config.set("werewolf_vote_enabled", False)
        self.clear_votes()
        return "🔴 رأی خودکار خاموش شد و همهٔ رأی‌ها پاک شدند."

    def _load_games(self):
        saved = self.config.get("werewolf_game_votes", {})
        if not isinstance(saved, dict):
            return
        for group_id, votes in saved.items():
            if not str(group_id).lstrip("-").isdigit():
                continue
            state = self._state(int(group_id), create=True, manual=True)
            for vote in votes if isinstance(votes, list) else []:
                try:
                    state["normal_votes"].append(
                        _target_record(vote["id"], vote.get("name", ""))
                    )
                except (KeyError, TypeError, ValueError):
                    continue

    def _save_games(self):
        payload = {}
        for group_id, state in self.games.items():
            if state["normal_votes"]:
                payload[str(group_id)] = list(state["normal_votes"])
        self.config.set("werewolf_game_votes", payload)

    def clear_votes(self, group_id=None):
        if group_id is None:
            for state in self.games.values():
                self._clear_state_votes(state)
        else:
            state = self._state(group_id)
            if state:
                self._clear_state_votes(state)
        self._save_games()

    async def register_vote(self, group_id, target_id, name=""):
        state = self._state(group_id, create=True, manual=True)
        vote = _target_record(target_id, name)
        if state["waiting_trouble_prompt"] is not None:
            message = state["waiting_trouble_prompt"]
            state["waiting_trouble_prompt"] = None
            success, detail, missing = await self._click_vote(message, vote)
            if success:
                return f"✅ رأی دوم دردسر برای {vote['name']} ثبت شد."
            if missing:
                await self._quick_notice(
                    group_id,
                    "❌ شخص در فهرست زنده‌ها پیدا نشد؛ یک رأی جدید برای اعدام امشب انتخاب کنید."
                )
            return f"❌ رأی دوم ثبت نشد: {detail}"

        state["normal_votes"].append(vote)
        self._save_games()
        position = len(state["normal_votes"])
        return f"✅ رأی {vote['name']} با شمارهٔ {position} ثبت شد."

    def remove_vote(self, group_id, index):
        state = self._state(group_id)
        if not state or index > len(state["normal_votes"]):
            return "❌ شمارهٔ رأی پیدا نشد."
        votes = list(state["normal_votes"])
        removed = votes.pop(index - 1)
        state["normal_votes"] = deque(votes)
        self._save_games()
        return f"✅ رأی شمارهٔ {index} برای {removed['name']} حذف شد."

    def change_vote(self, group_id, index, target_id, name=""):
        state = self._state(group_id)
        if not state or index > len(state["normal_votes"]):
            return "❌ شمارهٔ رأی پیدا نشد."
        votes = list(state["normal_votes"])
        old = votes[index - 1]
        votes[index - 1] = _target_record(target_id, name)
        state["normal_votes"] = deque(votes)
        self._save_games()
        return f"✅ رأی شمارهٔ {index} از {old['name']} به {name} تغییر کرد."

    def get_vote_panel_text(self):
        status = "🟢 روشن" if self.is_vote_enabled() else "🔴 خاموش"
        tracked = sum(1 for state in self.games.values() if state["owner_joined"])
        votes = sum(len(state["normal_votes"]) for state in self.games.values())
        return (
            "🗳 رأی خودکار گرگینه\n\n"
            f"وضعیت: {status}\n"
            f"گروه‌های بازی: {tracked}\n"
            f"کل رأی‌های ذخیره‌شده: {votes}\n\n"
            "برای دستورها، دکمهٔ «راهنما» را بزنید."
        )

    def get_help_text(self):
        return (
            "📖 راهنمای گرگینه\n\n"
            "آموزش نقش:\n"
            "آموزش دردسر\n\n"
            "مدیریت گروه بازی:\n"
            "گرگینه اینجا | گرگینه حذف\n"
            "وضعیت روستا\n\n"
            "رأی خودکار:\n"
            "رای روشن | رای خاموش\n"
            "رای 123456789 | رای @username\n"
            "رای خالی + ریپلای روی پیام شخص\n"
            "حذف رای 2\n"
            "تغییر رای 2 @username\n"
            "تغییر رای 2 + ریپلای روی پیام شخص\n\n"
            "بازی بعدی:\n"
            "نکست | next | لغو نکست"
        )

    # ─────────────────────────────────────────
    # تشخیص استارت، لیست بازیکنان و پایان بازی
    # ─────────────────────────────────────────

    async def handle_bot_message(self, event, edited=False):
        text = _compact(event.raw_text)
        if not text:
            return

        # دستور استارت هر کاربر، محدودهٔ جست‌وجوی همان گروه را مشخص می‌کند.
        if event.sender_id != WEREWOLF_BOT_ID:
            match = START_COMMAND_RE.fullmatch(text)
            if match and not event.is_private:
                mode = "chaos" if match.group(1).lower() == "startchaos" else "normal"
                state = self._state(event.chat_id, create=True, mode=mode)
                state["start_message_id"] = event.id
                asyncio.create_task(self._scan_near_start(event.chat_id, event.id))
            return

        if event.is_private:
            if self._is_next_notification(text):
                await self._schedule_auto_join(event.message)
                return
            if any(part in text for part in ASK_LYNCH_PARTS) and event.message.buttons:
                await self._handle_lynch_prompt(event.message)
            elif "امروز رای گیری نداریم" in text or "امروز رای‌گیری نداریم" in text:
                for state in self.games.values():
                    if state["current_attempt"] or state["waiting_trouble_prompt"]:
                        await self._handle_peace(state)
            elif TIMES_UP in text:
                state = self._state_for_prompt(event.message)
                if state:
                    state["current_attempt"] = None
                    state["waiting_trouble_prompt"] = None
            return

        await self._handle_group_bot_message(event.chat_id, event.message, text)

    async def _scan_recent_group(self, group_id):
        try:
            messages = await self.client.get_messages(group_id, limit=50)
            for message in reversed(list(messages)):
                if getattr(message, "sender_id", None) != WEREWOLF_BOT_ID:
                    continue
                text = _compact(getattr(message, "raw_text", ""))
                if text:
                    await self._handle_group_bot_message(group_id, message, text)
        except Exception:
            pass

    async def _scan_near_start(self, group_id, start_message_id):
        for _ in range(5):
            await asyncio.sleep(2)
            try:
                messages = await self.client.get_messages(group_id, limit=25)
                for message in reversed(list(messages)):
                    if getattr(message, "id", 0) < start_message_id:
                        continue
                    if getattr(message, "sender_id", None) != WEREWOLF_BOT_ID:
                        continue
                    text = _compact(getattr(message, "raw_text", ""))
                    if text:
                        await self._handle_group_bot_message(group_id, message, text)
                state = self._state(group_id)
                if state and state["owner_joined"] and state["player_count"]:
                    return
            except Exception:
                pass

    async def _handle_group_bot_message(self, group_id, message, text):
        if "یک بازی با حالت آشوب" in text and "ساخته شده" in text:
            state = self._state(group_id, create=True, mode="chaos")
            state["join_token"] = self._join_token_from_message(message)
        elif "یک بازی توسط" in text and "ساخته شده" in text:
            state = self._state(group_id, create=True, mode="normal")
            state["join_token"] = self._join_token_from_message(message)
        else:
            state = self._state(group_id)

        player_match = PLAYER_LIST_RE.search(text)
        if player_match:
            state = state or self._state(group_id, create=True)
            state["player_count"] = int(player_match.group(1))
            if self._message_has_owner(message, text) or state["manual"]:
                state["owner_joined"] = True
                state["started"] = True
                self._save_games()

        if NOT_ENOUGH_TEXT in text:
            self.reset_group(group_id, remove=True)
            return
        if not state:
            return

        if _compact(START_TEXT) in text and state["owner_joined"]:
            state["started"] = True

        alive_match = ALIVE_LIST_RE.search(text)
        if alive_match:
            state["alive_count"] = int(alive_match.group(1))
            state["player_count"] = int(alive_match.group(2))
            if self._owner_is_dead_in_list(message, text):
                self.clear_votes(group_id)

        if "بخاطر مشکلات ایجاد شده شما امروز دوبار رای گیری میکنید" in text or \
                "بخاطر مشکلات ایجاد شده شما امروز دو بار رای گیری میکنید" in text:
            state["next_prompt_is_trouble"] = True

        if "امروز رای گیری نداریم" in text or "امروز رای‌گیری نداریم" in text:
            await self._handle_peace(state)

        if END_GAME_RE.search(text) and ALIVE_LIST_RE.search(text):
            self.reset_group(group_id, remove=True)

    def _join_token_from_message(self, message):
        for row in message.buttons or []:
            for button in row:
                url = getattr(button, "url", "") or ""
                match = re.search(r"[?&]start=(join[^&\s]+)", url, re.IGNORECASE)
                if match:
                    return match.group(1)[4:]
        return None

    def _message_has_owner(self, message, text):
        if not self.owner_id:
            return False
        for entity in getattr(message, "entities", None) or []:
            if getattr(entity, "user_id", None) == self.owner_id:
                return True
            if f"user?id={self.owner_id}" in (getattr(entity, "url", "") or ""):
                return True
        lowered = text.lower()
        return any(name and name in lowered for name in self.owner_names)

    def _owner_is_dead_in_list(self, message, text):
        if not self.owner_id:
            return False
        try:
            from telethon.helpers import add_surrogate
            surrogate = add_surrogate(message.raw_text or "")
            for entity in message.entities or []:
                is_owner = (
                    getattr(entity, "user_id", None) == self.owner_id
                    or f"user?id={self.owner_id}" in (getattr(entity, "url", "") or "")
                )
                if not is_owner:
                    continue
                start = surrogate.rfind("\n", 0, entity.offset) + 1
                end = surrogate.find("\n", entity.offset + entity.length)
                if end < 0:
                    end = len(surrogate)
                return "مرده" in surrogate[start:end]
        except Exception:
            pass
        for name in self.owner_names:
            for line in text.lower().splitlines():
                if name in line and "مرده" in line:
                    return True
        return False

    # ─────────────────────────────────────────
    # اتصال منوی خصوصی رأی به بازی درست
    # ─────────────────────────────────────────

    def _prompt_token(self, message):
        for row in message.buttons or []:
            for button in row:
                data = getattr(button, "data", b"") or b""
                try:
                    parts = data.decode().split("|")
                except UnicodeDecodeError:
                    continue
                if len(parts) >= 5 and parts[0] == "vote":
                    return parts[1] + parts[2]
        return None

    def _state_for_prompt(self, message):
        message_id = getattr(message, "id", None)
        if message_id is not None:
            for state in self.games.values():
                attempt = state["current_attempt"] or {}
                waiting = state["waiting_trouble_prompt"]
                if attempt.get("prompt_id") == message_id:
                    return state
                if waiting is not None and getattr(waiting, "id", None) == message_id:
                    return state
        token = self._prompt_token(message)
        if token:
            for state in self.games.values():
                if state["join_token"] == token:
                    return state
        active = [s for s in self.games.values() if s["owner_joined"]]
        return active[0] if len(active) == 1 else None

    async def _handle_lynch_prompt(self, message):
        if not self.is_vote_enabled():
            return
        state = self._state_for_prompt(message)
        if not state:
            return

        is_trouble = state["next_prompt_is_trouble"]
        state["next_prompt_is_trouble"] = False
        if is_trouble:
            state["waiting_trouble_prompt"] = message
            await self._quick_notice(
                state["group_id"],
                "🤯 دردسر فعال است؛ برای رأی دوم یک نفر را انتخاب کنید. رأی دور بعد مصرف نمی‌شود."
            )
            return

        if not state["normal_votes"]:
            await self._quick_notice(
                state["group_id"], "🗳 برای اعدام امشب رأی ذخیره‌شده‌ای ندارید."
            )
            return

        vote = state["normal_votes"].popleft()
        self._save_games()
        state["current_attempt"] = {
            "kind": "normal",
            "vote": vote,
            "prompt_id": getattr(message, "id", None),
        }
        success, detail, missing = await self._click_vote(message, vote)
        if success:
            state["current_attempt"]["accepted"] = True
            return
        state["current_attempt"] = None
        if missing:
            await self._quick_notice(
                state["group_id"],
                "❌ شخص در فهرست زنده‌ها پیدا نشد؛ یک رأی جدید برای اعدام امشب انتخاب کنید."
            )
        else:
            state["normal_votes"].appendleft(vote)
            self._save_games()
            await self._quick_notice(
                state["group_id"], f"❌ رأی خودکار ثبت نشد: {detail}"
            )

    async def _handle_peace(self, state):
        attempt = state["current_attempt"]
        if attempt and attempt.get("kind") == "normal":
            vote = attempt["vote"]
            if (not state["normal_votes"]
                    or state["normal_votes"][0]["id"] != vote["id"]):
                state["normal_votes"].appendleft(vote)
        state["current_attempt"] = None
        state["waiting_trouble_prompt"] = None
        state["trouble_vote"] = None
        state["next_prompt_is_trouble"] = False
        self._save_games()

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
                return False, "بازیکن در فهرست زنده‌ها نیست", True
            last_error = "پاسخ تأیید دریافت نشد"
            for attempt in range(2):
                if attempt:
                    await asyncio.sleep(3)
                try:
                    answer = await message.click(data=button.data)
                    answer_text = _compact(getattr(answer, "message", ""))
                    if CHOICE_ACCEPTED in answer_text:
                        return True, answer_text, False
                    if TIMES_UP in answer_text:
                        return False, "وقت رأی‌گیری تمام شد", False
                    if answer_text:
                        last_error = answer_text
                except Exception as exc:
                    last_error = str(exc)[:120]
            return False, last_error, False

    async def _quick_notice(self, group_id, text, seconds=7):
        try:
            message = await self.client.send_message(group_id, text)
        except Exception:
            return

        async def remove_later():
            await asyncio.sleep(seconds)
            try:
                await message.delete()
            except Exception:
                pass

        asyncio.create_task(remove_later())

    # ─────────────────────────────────────────
    # وضعیت روستا
    # ─────────────────────────────────────────

    def get_village_status(self, group_id):
        state = self._state(group_id)
        if not state or not state["owner_joined"] or not state["player_count"]:
            return "❌ هنوز حضور شما در فهرست بازیکنان این گروه شناسایی نشده است."
        count = state["player_count"]
        wolves = min(max(count // 5, 1), 5)
        max_negative = (count - 1) // 2
        min_village = count - max_negative
        max_village = count - wolves
        mode = {"normal": "معمولی", "chaos": "آشوب", "unknown": "نامشخص"}[state["mode"]]
        alive = f"\n🙂 بازیکنان زنده: {state['alive_count']}" if state["alive_count"] else ""
        return (
            "🐺 **وضعیت احتمالی روستا**\n\n"
            f"🎮 مود: {mode}\n"
            f"👥 بازیکنان شروع: {count}{alive}\n"
            f"🐺 گرگ‌های اولیه: حدود {wolves}\n"
            f"🔴 منفی/مستقل: بین {wolves} تا {max_negative}\n"
            f"🟢 روستایی: بین {min_village} تا {max_village}\n\n"
            "ترکیب دقیق مخفی است و تبدیل نقش‌ها می‌تواند وضعیت را تغییر دهد."
        )

    # ─────────────────────────────────────────
    # انتظار بازی بعدی و جوین خودکار
    # ─────────────────────────────────────────

    def _save_next_groups(self):
        self.config.set("werewolf_next_group_ids", sorted(self.next_group_ids))

    def set_next_wait(self, group_id):
        self.next_group_ids.add(int(group_id))
        self._save_next_groups()

    def clear_next_wait(self, group_id=None):
        if group_id is None:
            self.next_group_ids.clear()
        else:
            self.next_group_ids.discard(int(group_id))
        self._save_next_groups()

    async def cancel_next_wait(self, group_id=None):
        wanted = int(group_id) if group_id else None
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
                        if wanted and button_group != wanted:
                            continue
                        answer = await message.click(data=data)
                        self.clear_next_wait(button_group)
                        return True, _compact(getattr(answer, "message", "")) or "لغو شد"
        except Exception as exc:
            return False, str(exc)[:120]
        return False, "دکمهٔ کنسل پیدا نشد"

    def _is_next_notification(self, text):
        return "هورا یه بازی جدید توی گروه" in text and "شروع شده" in text

    async def _schedule_auto_join(self, notification):
        key = getattr(notification, "id", id(notification))
        task = self.next_join_tasks.get(key)
        if task and not task.done():
            return
        self.next_join_tasks[key] = asyncio.create_task(
            self._auto_join_next_game(notification)
        )

    async def _auto_join_next_game(self, notification):
        async with self.next_join_lock:
            group = await self._group_from_notification(notification)
            if group is None and len(self.next_group_ids) == 1:
                try:
                    group = await self.client.get_entity(next(iter(self.next_group_ids)))
                except Exception:
                    group = None
            if group is None:
                return
            group_id = getattr(group, "id", group)
            for _ in range(6):
                try:
                    messages = await self.client.get_messages(group, limit=30)
                    for message in messages:
                        if getattr(message, "sender_id", None) != WEREWOLF_BOT_ID:
                            continue
                        token = self._join_token_from_message(message)
                        if token:
                            await self.client.send_message(
                                WEREWOLF_BOT_ID, f"/start join{token}"
                            )
                            self.clear_next_wait(group_id)
                            return
                except Exception:
                    pass
                await asyncio.sleep(2)

    async def _group_from_notification(self, message):
        for entity in getattr(message, "entities", None) or []:
            url = getattr(entity, "url", None)
            if not url:
                continue
            try:
                public = re.search(r"t\.me/([A-Za-z][A-Za-z0-9_]{3,})", url)
                if public and public.group(1).lower() not in ("joinchat", "werewolfbot"):
                    return await self.client.get_entity(public.group(1))
                invite = re.search(r"t\.me/(?:joinchat/|\+)([A-Za-z0-9_-]+)", url)
                if invite:
                    from telethon.tl.functions.messages import CheckChatInviteRequest
                    checked = await self.client(CheckChatInviteRequest(invite.group(1)))
                    if getattr(checked, "chat", None):
                        return checked.chat
            except Exception:
                continue
        return None
