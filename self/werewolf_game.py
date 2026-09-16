"""ردیابی چند بازی گرگینه، وضعیت روستا و رأی خودکار.

فقط پیام‌های ربات رسمی Werewolf پردازش می‌شوند. هر گروه وضعیت و صف رأی
مستقل دارد و منوی خصوصی رأی از روی شناسهٔ بازی داخل callback به گروه درست
وصل می‌شود.

تغییرات نسخه جدید:
  - نکست: پیدا کردن خودکار دکمهٔ «وارید شوید» زیر گیف استارت، استارت
    بازی با همان لینک و انتظار ۱۰ ثانیه‌ای برای پیام «با موفقیت وارد بازی
    شدید»؛ اگر نیامد دوباره با همان لینک استارت می‌کند (۳ بار)
  - حذف خودکار رأی بعد از ثبت موفق (تأیید سه‌راهی: توست دکمه، پیام خصوصی
    «انتخاب پذیرفته شد» و اعلام عمومی «نظرش اینه که ... اعدام بشه») و
    رفتن سراغ رأی بعدی در شب‌های بعد
  - با پایان شب (وقت تموم شد / لغو رأی‌گیری) رأیِ همان شب به‌کل کنسل و
    حذف می‌شود و منتظر شب بعدی می‌ماند
  - سیستم رأی دردسر جداگانه (رای درد 1 / رای درد 2) با دو راند
    رأی‌گیری همان روز؛ تشخیص اعلام دردسر داخل گروه
  - دکمه‌های نقش (آتیش، گرگ و...) هرگز کلیک نمی‌شوند؛ فقط دکمهٔ رأیِ
    متناظر با آیدی هدفِ ذخیره‌شده لمس می‌شود
  - ردیابی روز/شب بازی
  - فعال‌سازی ساده با «گرگینه» و غیرفعال با «حذف گرگینه»
"""

import asyncio
import re
import time
from collections import deque


WEREWOLF_BOT_ID = 175844556
WEREWOLF_BETA_BOT_ID = 198626752
WEREWOLF_BOT_IDS = {WEREWOLF_BOT_ID, WEREWOLF_BETA_BOT_ID}
START_TEXT = "ایول بازی شروع شد 😃 یه کم صبر کنین نقشاتونو بهتون بگم"
NOT_ENOUGH_TEXT = "چقدر کمین! من با این تعداد بازیکن بازی رو شروع نمیکنم"

# متن‌های منوی رأی اعدام (فقط همین متن‌ها منوی رأی حساب می‌شوند؛
# منوهای نقش مثل آتیش/گرگ هرگز این متن‌ها را ندارند)
ASK_LYNCH_PARTS = (
    "به کی رای میدی که اعدام بشه",
    "کیو میخواین اعدام کنین",
    "وقت دارین رای بدین",
)
CHOICE_ACCEPTED = "انتخاب پذیرفته شد"
ALREADY_VOTED_MARKS = ("قبلا رای", "قبلاً رای", "قبلا به این")
TIMES_UP = "وقت تموم شد"

# اعلام عمومی رأی داخل گروه: «X نظرش اینه که Y اعدام بشه»
VOTE_ANNOUNCE_MARK = "نظرش این"
VOTE_ANNOUNCE_WORD = "اعدام"

# پیام موفقیت ورود به بازی (پیوی ربات)
JOIN_SUCCESS_MARKS = ("با موفقیت وارد بازی",)
JOIN_ALREADY_MARKS = ("قبلا وارد",)
# اطلاعیهٔ «بازی جدید شروع شد» برای نکست
NEXT_NOTIFY_MARKS = ("هورا یه بازی جدید توی گروه",)
PEACE_MARKS = ("امروز رای گیری نداریم", "امروز رای‌گیری نداریم")

PLAYER_LIST_RE = re.compile(r"#players\s*:\s*(\d+)", re.IGNORECASE)
ALIVE_LIST_RE = re.compile(r"بازیکن[‌ ]های زنده\s*:\s*(\d+)\s*/\s*(\d+)")
END_GAME_RE = re.compile(r"مدت\s*زمان\s*بازی\s*:")
CALLBACK_TARGET_RE = re.compile(rb"\|(-?\d+)$")
START_COMMAND_RE = re.compile(
    r"^/(startchaos|startgame)(?:@werewolfbot)?$", re.IGNORECASE
)
VALID_TARGET_RE = re.compile(r"^(?:@?[A-Za-z0-9_]{3,}|\d{5,})$")

# «☀️ روز 2» / «🌙 شب 3» — فقط ابتدای پیام
PHASE_RE = re.compile(r"^\s*(?:[^\sa-zA-Z0-9]{1,6}\s*)?(روز|شب)\s*([0-9۰-۹]+)")

FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

JOIN_ATTEMPTS = 3          # تعداد استارت برای ورود خودکار
JOIN_CONFIRM_TIMEOUT = 10  # ثانیه انتظار برای «وارد بازی شدید»
JOIN_SCAN_ROUNDS = 6       # دورهای جستجوی دکمهٔ وارید شوید
VOTE_CONFIRM_TIMEOUT = 7   # ثانیه انتظار برای اعلام رأی در گروه
# جلوگیری از پردازش دوبارهٔ همان منو (ویرایش شمارش معکوس و...) —
# کل پنجرهٔ ۹۰ ثانیه‌ای رأی‌گیری پوشش داده شود
PROMPT_DEDUP_SECONDS = 120
TROUBLE_ROUND_GAP = 45     # حداقل فاصلهٔ دو راند دردسر روی همان پیام


def _compact(text):
    return " ".join((text or "").replace("ي", "ی").replace("ك", "ک").split())


def _target_record(target_id, name=""):
    return {"id": int(target_id), "name": (name or str(target_id)).strip()}


def is_vote_registration(text, is_reply=False):
    """«رای» ریپلای‌شده یا «رای شناسه» — رأی عادی."""
    text = (text or "").strip()
    if is_reply:
        return text == "رای"
    if not text.startswith("رای "):
        return False
    target = text[4:].strip()
    return bool(VALID_TARGET_RE.fullmatch(target))


def is_trouble_vote_registration(text, is_reply=False):
    """«رای درد» ریپلای‌شده یا «رای درد شناسه» — رأی دردسر."""
    text = (text or "").strip()
    if is_reply:
        return text in ("رای درد", "رای درد 1", "رای درد 2")
    for prefix in ("رای درد 1 ", "رای درد 2 ", "رای درد "):
        if text.startswith(prefix):
            target = text[len(prefix):].strip()
            if VALID_TARGET_RE.fullmatch(target):
                return True
    return False


def parse_trouble_slot(text):
    """شماره اسلات دردسر (1 یا 2) را استخراج می‌کند. پیش‌فرض 1."""
    text = (text or "").strip()
    if text.startswith("رای درد 2") or text == "رای درد 2":
        return 2
    return 1


def parse_vote_index_command(text, prefix):
    text = (text or "").strip()
    if not text.startswith(prefix + " "):
        return None
    rest = text[len(prefix):].strip()
    first = rest.split(maxsplit=1)[0] if rest else ""
    return int(first) if first.isdigit() and int(first) > 0 else None


def _is_trouble_announcement(text):
    """اعلان دردسرساز داخل گروه — امروز دو بار رأی‌گیری می‌شود."""
    if "بخاطر مشکلات ایجاد شده" in text:
        return True
    has_vote_word = "رای گیری" in text or "رای‌گیری" in text
    has_double = "دوبار" in text or "دو بار" in text
    return bool(has_vote_word and has_double)


def _parse_phase(text):
    """«☀️ روز 2» یا «🌙 شب 3» → (phase, number)."""
    match = PHASE_RE.match(text or "")
    if not match:
        return None
    number = int(match.group(2).translate(FA_DIGITS))
    return ("day" if match.group(1) == "روز" else "night"), number


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
        self.join_tasks = {}
        self.join_confirm = None
        # نگهبانان تأیید رأی: منتظر توست/پیام خصوصی/اعلام گروه
        self.vote_watchers = []
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

    def _new_state(self, group_id, mode="unknown", manual=False,
                   bot_id=WEREWOLF_BOT_ID, bot_name="werewolfbot",
                   group_name=""):
        return {
            "group_id": int(group_id),
            "mode": mode,
            "manual": manual,
            "owner_joined": manual,
            "started": False,
            "player_count": 0,
            "alive_count": 0,
            "join_token": None,
            "enabled": True,
            "bot_id": bot_id,
            "bot_name": bot_name,
            "group_name": group_name,
            # صف رأی عادی
            "normal_votes": deque(),
            # رأی‌های دردسر (حداکثر ۲ اسلات)
            "trouble_votes": [None, None],
            "trouble_mode": False,
            "trouble_prompts": 0,
            "waiting_trouble_prompt": None,
            "current_attempt": None,
            "last_prompt_id": None,
            "last_prompt_ts": 0.0,
            "phase": None,
            "day_number": 0,
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
        # مهاجرت از نسخه‌های قبلی
        if state:
            state.setdefault("trouble_votes", [None, None])
            state.setdefault("trouble_mode", False)
            state.setdefault("trouble_prompts", 0)
            state.setdefault("waiting_trouble_prompt", None)
            state.setdefault("current_attempt", None)
            state.setdefault("last_prompt_id", None)
            state.setdefault("last_prompt_ts", 0.0)
            state.setdefault("phase", None)
            state.setdefault("day_number", 0)
        return state

    def track_group_manually(self, group_id, group_name="",
                             bot_id=WEREWOLF_BOT_ID,
                             bot_name="werewolfbot"):
        state = self._state(group_id, create=True, manual=True)
        if group_name:
            state["group_name"] = group_name
        if bot_id != WEREWOLF_BOT_ID:
            state["bot_id"] = bot_id
        if bot_name != "werewolfbot":
            state["bot_name"] = bot_name
        state["enabled"] = True
        self._save_games()
        try:
            asyncio.create_task(self._scan_recent_group(group_id))
        except RuntimeError:
            pass
        return "✅ گرگینه فعال شد (@%s)" % bot_name

    def untrack_group(self, group_id):
        state = self.games.pop(int(group_id), None)
        self._save_games()
        if state:
            return "✅ گرگینه برای این گروه غیرفعال شد."
        return "❌ گرگینه در این گروه فعال نبود."

    def is_tracked_group(self, group_id):
        state = self._state(group_id)
        return bool(state and state["owner_joined"])

    def _clear_state_votes(self, state):
        state["normal_votes"].clear()
        state["trouble_votes"] = [None, None]
        state["trouble_mode"] = False
        state["trouble_prompts"] = 0
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
            state["phase"] = None
            state["day_number"] = 0
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
        return "✅ رأی خودکار روشن شد."

    def disable_votes(self):
        self.config.set("werewolf_vote_enabled", False)
        self.clear_votes()
        return "🔴 رأی خودکار خاموش شد."

    def _load_games(self):
        saved = self.config.get("werewolf_game_votes", {})
        if not isinstance(saved, dict):
            return
        for group_id, data in saved.items():
            if not str(group_id).lstrip("-").isdigit():
                continue
            state = self._state(int(group_id), create=True, manual=True)
            if isinstance(data, dict):
                for vote in data.get("normal", []):
                    try:
                        state["normal_votes"].append(
                            _target_record(vote["id"], vote.get("name", ""))
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
                for i, tv in enumerate(data.get("trouble", [None, None])):
                    if tv and i < 2:
                        try:
                            state["trouble_votes"][i] = _target_record(
                                tv["id"], tv.get("name", "")
                            )
                        except (KeyError, TypeError, ValueError):
                            pass
            elif isinstance(data, list):
                for vote in data:
                    try:
                        state["normal_votes"].append(
                            _target_record(vote["id"], vote.get("name", ""))
                        )
                    except (KeyError, TypeError, ValueError):
                        continue

    def _save_games(self):
        payload = {}
        for group_id, state in self.games.items():
            has_data = (
                state["normal_votes"]
                or any(v is not None for v in state["trouble_votes"])
            )
            if has_data:
                payload[str(group_id)] = {
                    "normal": list(state["normal_votes"]),
                    "trouble": state["trouble_votes"],
                }
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

    # ─── رأی عادی ───

    async def register_vote(self, group_id, target_id, name=""):
        state = self._state(group_id, create=True, manual=True)
        vote = _target_record(target_id, name)

        # اگر منتظر رأی دستی دردسر هستیم، همین الان کلیک می‌شود
        waiting = state.get("waiting_trouble_prompt")
        if waiting is not None:
            state["waiting_trouble_prompt"] = None
            status, detail = await self._click_vote(waiting, vote)
            if status == "ok":
                if state.get("trouble_prompts", 0) >= 2:
                    state["trouble_mode"] = False
                self._save_games()
                return "✅ رأی دردسر برای %s همان لحظه ثبت شد." % vote["name"]
            state["normal_votes"].append(vote)
            self._save_games()
            return "⚠️ کلیک نشد (%s)؛ به‌عنوان رأی عادی ذخیره شد." % detail

        state["normal_votes"].append(vote)
        self._save_games()
        position = len(state["normal_votes"])
        return "✅ رأی `%d` برای %s ثبت شد." % (position, vote["name"])

    def remove_vote(self, group_id, index):
        state = self._state(group_id)
        if not state or index is None or index < 1 or index > len(state["normal_votes"]):
            return "❌ شمارهٔ رأی پیدا نشد."
        votes = list(state["normal_votes"])
        removed = votes.pop(index - 1)
        state["normal_votes"] = deque(votes)
        self._save_games()
        return "✅ رأی `%d` (%s) حذف شد." % (index, removed["name"])

    def change_vote(self, group_id, index, target_id, name=""):
        state = self._state(group_id)
        if not state or index is None or index < 1 or index > len(state["normal_votes"]):
            return "❌ شمارهٔ رأی پیدا نشد."
        votes = list(state["normal_votes"])
        old = votes[index - 1]
        votes[index - 1] = _target_record(target_id, name)
        state["normal_votes"] = deque(votes)
        self._save_games()
        return "✅ رأی `%d` از %s به %s تغییر کرد." % (index, old["name"], name)

    # ─── رأی دردسر ───

    async def register_trouble_vote(self, group_id, slot, target_id, name=""):
        """ثبت رأی دردسر (اسلات 1 یا 2).

        اگر ربات همین حالا منتظر رأی دردسر باشد (راند دردسر باز است)،
        رأی بلافاصله روی همان منو کلیک می‌شود.
        """
        state = self._state(group_id, create=True, manual=True)
        idx = max(0, min(slot - 1, 1))
        vote = _target_record(target_id, name)

        waiting = state.get("waiting_trouble_prompt")
        if waiting is not None:
            state["waiting_trouble_prompt"] = None
            status, detail = await self._click_vote(waiting, vote)
            if status == "ok":
                if state.get("trouble_prompts", 0) >= 2:
                    state["trouble_mode"] = False
                self._save_games()
                return "✅ رأی درد `%d` برای %s همان لحظه ثبت شد." % (
                    slot, vote["name"]
                )
            state["trouble_votes"][idx] = vote
            self._save_games()
            return "⚠️ کلیک نشد (%s)؛ رأی درد `%d` ذخیره شد." % (detail, slot)

        old = state["trouble_votes"][idx]
        state["trouble_votes"][idx] = vote
        self._save_games()
        old_text = " (قبلی: %s)" % old["name"] if old else ""
        return "✅ رأی درد `%d` برای %s ثبت شد.%s" % (slot, vote["name"], old_text)

    def remove_trouble_vote(self, group_id, slot):
        """حذف رأی دردسر."""
        state = self._state(group_id)
        if not state:
            return "❌ گروه پیدا نشد."
        idx = max(0, min(slot - 1, 1))
        old = state["trouble_votes"][idx]
        if not old:
            return "❌ رأی درد `%d` خالی است." % slot
        state["trouble_votes"][idx] = None
        self._save_games()
        return "✅ رأی درد `%d` (%s) حذف شد." % (slot, old["name"])

    def change_trouble_vote(self, group_id, slot, target_id, name=""):
        """تغییر رأی دردسر."""
        state = self._state(group_id)
        if not state:
            return "❌ گروه پیدا نشد."
        idx = max(0, min(slot - 1, 1))
        old = state["trouble_votes"][idx]
        vote = _target_record(target_id, name)
        state["trouble_votes"][idx] = vote
        self._save_games()
        old_name = old["name"] if old else "خالی"
        return "✅ رأی درد `%d` از %s به %s تغییر کرد." % (slot, old_name, name)

    # ─── متن پنل ───

    def get_vote_panel_text(self):
        status = "🟢 روشن" if self.is_vote_enabled() else "🔴 خاموش"
        tracked = sum(1 for s in self.games.values() if s["owner_joined"])
        total_normal = sum(len(s["normal_votes"]) for s in self.games.values())
        total_trouble = sum(
            sum(1 for v in s["trouble_votes"] if v is not None)
            for s in self.games.values()
        )

        text = "🗳 **رأی خودکار گرگینه**\n\n"
        text += "  ▸ وضعیت: %s\n" % status
        text += "  ▸ گروه‌های بازی: `%d`\n" % tracked
        text += "  ▸ رأی‌های عادی: `%d`\n" % total_normal
        text += "  ▸ رأی‌های دردسر: `%d`\n\n" % total_trouble

        for gid, state in self.games.items():
            if not state["owner_joined"]:
                continue
            if not state["normal_votes"] and not any(state["trouble_votes"]):
                continue
            text += "💬 گروه `%s`:\n" % (state.get("group_name") or gid)
            if state["normal_votes"]:
                for i, v in enumerate(state["normal_votes"], 1):
                    text += "  🔹 رأی `%d`: %s\n" % (i, v["name"])
            for i, tv in enumerate(state["trouble_votes"], 1):
                if tv:
                    text += "  🤯 درد `%d`: %s\n" % (i, tv["name"])
            text += "\n"

        return text

    def get_help_text(self):
        return (
            "📖 **راهنما**\n\n"

            "**🐺 فعال‌سازی:**\n"
            "`گرگینه` → فعال‌سازی در گروه فعلی\n"
            "`حذف گرگینه` → غیرفعال‌سازی (یا از پنل)\n\n"

            "**📊 وضعیت:**\n"
            "`وضعیت روستا`\n\n"

            "**⏭ بازی بعدی:**\n"
            "`نکست` → انتظار بازی جدید و ورود خودکار\n"
            "دکمهٔ «وارید شوید» زیر گیف خودکار زده می‌شود؛\n"
            "اگر تا ۱۰ ثانیه پیام «وارد بازی شدید» نیاید،\n"
            "دوباره با همان لینک استارت می‌کند.\n"
            "`لغو نکست`\n\n"

            "**🗳 رأی خودکار:**\n"
            "`رای روشن` | `رای خاموش`\n"
            "`رای` + ریپلای روی پیام شخص\n"
            "`رای @username` | `رای 123456789`\n"
            "`حذف رای 1`\n"
            "`تغییر رای 1 @username` | `تغییر رای 1` + ریپلای\n\n"

            "**🤯 رأی دردسر (۲ رأی همان روز):**\n"
            "`رای درد 1` + ریپلای\n"
            "`رای درد 1 @username` | `رای درد 1 123456789`\n"
            "`رای درد 2 @username`\n"
            "`حذف رای درد 1`\n"
            "`تغییر رای درد 1 @username` | `تغییر رای درد 1` + ریپلای\n\n"

            "**📓 نکتهٔ رأی‌ها:**\n"
            "هر شب فقط یک رأی از صف استفاده می‌شود؛\n"
            "بعد از ثبت موفق (انتخاب پذیرفته شد) همان رأی\n"
            "حذف می‌شود و شب بعد سراغ رأی بعدی می‌رود.\n"
            "با پایان هر شب، رأیِ آن شب به‌کل کنسل می‌شود.\n"
            "دکمه‌های نقش (آتیش، گرگ و...) هرگز زده نمی‌شوند.\n\n"

            "**📖 آموزش نقش:**\n"
            "`آموزش دردسر` | `آموزش پیشگو`"
        )

    # ─────────────────────────────────────────
    # مسیر پیام‌های ربات گرگینه
    # ─────────────────────────────────────────

    async def handle_bot_message(self, event, edited=False):
        text = _compact(event.raw_text)
        if not text:
            return

        if event.sender_id not in WEREWOLF_BOT_IDS:
            # دستور استارت خودمان → فقط علامت‌گذاری گروه
            match = START_COMMAND_RE.fullmatch(text)
            if match and not event.is_private:
                mode = "chaos" if match.group(1).lower() == "startchaos" else "normal"
                state = self._state(event.chat_id, create=True, mode=mode)
                state["start_message_id"] = event.id
                asyncio.create_task(self._scan_near_start(event.chat_id, event.id))
            return

        if not event.is_private:
            await self._handle_group_message(event, text)
            return

        await self._handle_private_message(event, text)

    async def _handle_group_message(self, event, text):
        """پیام‌های ربات داخل گروه."""
        group_id = int(event.chat_id)
        state = self._state(group_id)
        if state and not state.get("enabled", True):
            return

        # ۱) نکست: دکمهٔ «وارید شوید» زیر گیف استارت بازی جدید
        if group_id in self.next_group_ids:
            token = self._join_token_from_message(event.message)
            if token:
                self._schedule_join_group(group_id, token)

        # ۲) تأیید رأی از اعلام عمومی گروه («نظرش اینه که ... اعدام بشه»)
        self._check_vote_confirmation(event.message, text)

        # ۳) منوی رأی اعدام (شب/روز رأی‌گیری)
        if any(part in text for part in ASK_LYNCH_PARTS) and event.message.buttons:
            await self._handle_lynch_prompt(event.message)
        elif any(mark in text for mark in PEACE_MARKS):
            for st in self.games.values():
                if st.get("current_attempt") or st.get("waiting_trouble_prompt"):
                    await self._cancel_night_vote(
                        st, "🕊 رأی‌گیری لغو شد؛ رأی این شب کنسل و حذف شد."
                    )
        elif TIMES_UP in text:
            st = self._state_for_prompt(event.message)
            if st:
                # اگر راند دردسر بعدی همان روز مانده، حالت دردسر حفظ شود
                keep = bool(
                    st.get("trouble_mode")
                    and st.get("trouble_prompts", 0) < 2
                )
                await self._cancel_night_vote(
                    st,
                    "⏰ وقت رأی‌گیری تمام شد؛ رأی این شب کنسل و حذف شد.",
                    keep_trouble=keep,
                )

        # ۴) بقیهٔ وضعیت بازی (استارت، لیست زنده‌ها، دردسر، پایان و...)
        await self._handle_group_bot_message(group_id, event.message, text)

    async def _handle_private_message(self, event, text):
        """پیام‌های ربات در پیوی."""
        message = event.message

        # ۱) پیام موفقیت ورود به بازی (تأیید نکست)
        if any(m in text for m in JOIN_SUCCESS_MARKS) or \
                any(m in text for m in JOIN_ALREADY_MARKS):
            group = await self._group_from_notification(message)
            if group is not None:
                gid = int(getattr(group, "id", group))
                state = self._state(gid, create=True, manual=True)
                state["owner_joined"] = True
                state["enabled"] = True
                self._save_games()
            if self.join_confirm is not None:
                self.join_confirm.set()
            return

        # ۲) اطلاعیهٔ «بازی جدید در گروه X شروع شد» → ورود خودکار نکست
        if any(m in text for m in NEXT_NOTIFY_MARKS):
            if self.next_group_ids:
                self._schedule_auto_join(message)
            return

        # ۳) تأیید رأی خصوصی («انتخاب پذیرفته شد»)
        self._check_vote_confirmation(message, text)

        # ۴) منوی خصوصی رأی اعدام
        if any(part in text for part in ASK_LYNCH_PARTS) and message.buttons:
            await self._handle_lynch_prompt(message)
            return

        await self._handle_group_bot_message(event.chat_id, message, text)

    async def _scan_recent_group(self, group_id):
        try:
            messages = await self.client.get_messages(group_id, limit=50)
            for message in reversed(list(messages)):
                if getattr(message, "sender_id", None) not in WEREWOLF_BOT_IDS:
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
                    if getattr(message, "sender_id", None) not in WEREWOLF_BOT_IDS:
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

        # ردیابی روز/شب («☀️ روز 2» / «🌙 شب 3»)
        phase = _parse_phase(text)
        if phase:
            state["phase"], state["day_number"] = phase

        if _compact(START_TEXT) in text and state["owner_joined"]:
            state["started"] = True

        alive_match = ALIVE_LIST_RE.search(text)
        if alive_match:
            state["alive_count"] = int(alive_match.group(1))
            state["player_count"] = int(alive_match.group(2))
            if self._owner_is_dead_in_list(message, text):
                self.clear_votes(group_id)

        # تشخیص دردسرساز: اعلام داخل گروه که امروز دو بار رأی‌گیری است
        if _is_trouble_announcement(text):
            state["trouble_mode"] = True
            state["trouble_prompts"] = 0
            state["waiting_trouble_prompt"] = None
            await self._quick_notice(
                group_id,
                "🤯 دردسرساز فعال شد! امروز دو راند رأی‌گیری داریم؛\n"
                "رأی‌های درد ۱ و ۲ خودکار ثبت می‌شوند."
            )

        if any(mark in text for mark in PEACE_MARKS):
            await self._cancel_night_vote(
                state, "🕊 امروز رأی‌گیری نداریم؛ رأی این شب کنسل و حذف شد."
            )

        if END_GAME_RE.search(text) and ALIVE_LIST_RE.search(text):
            self.reset_group(group_id, remove=True)

    def _join_token_from_message(self, message):
        """توکن بازی از دکمهٔ «وارید شوید» (لینک start=join...) زیر گیف."""
        fallback = None
        for row in message.buttons or []:
            for button in row:
                btn_text = getattr(button, "text", "") or ""
                url = getattr(button, "url", "") or ""
                match = re.search(r"[?&]start=(join[^&\s]+)", url, re.IGNORECASE)
                if not match:
                    continue
                token = match.group(1)[4:]
                # اولویت با دکمهٔ «وارید شوید»
                if "وارید" in btn_text or "ورود" in btn_text or "join" in btn_text.lower():
                    return token
                fallback = fallback or token
        return fallback

    def _message_has_owner(self, message, text):
        if not self.owner_id:
            return False
        for entity in getattr(message, "entities", None) or []:
            if getattr(entity, "user_id", None) == self.owner_id:
                return True
            if "user?id=%d" % self.owner_id in (getattr(entity, "url", "") or ""):
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
                    or "user?id=%d" % self.owner_id
                    in (getattr(entity, "url", "") or "")
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
                attempt = state.get("current_attempt") or {}
                waiting = state.get("waiting_trouble_prompt")
                if attempt.get("prompt_id") == message_id:
                    return state
                if waiting is not None and getattr(waiting, "id", None) == message_id:
                    return state
            for state in self.games.values():
                if state.get("last_prompt_id") == message_id:
                    return state
        token = self._prompt_token(message)
        if token:
            for state in self.games.values():
                if state["join_token"] == token:
                    return state
        active = [s for s in self.games.values() if s["owner_joined"]]
        return active[0] if len(active) == 1 else None

    # ─────────────────────────────────────────
    # کلیک رأی + تأیید سه‌راهی
    # ─────────────────────────────────────────

    def _vote_menu_buttons(self, message):
        """فقط دکمه‌های منوی رأی (کال‌بک با پیشوند vote)."""
        buttons = []
        for row in message.buttons or []:
            for button in row:
                data = getattr(button, "data", None)
                if data and data.split(b"|", 1)[0] == b"vote":
                    buttons.append(button)
        return buttons

    def _find_button(self, message, target_id):
        """دکمهٔ متناظر با آیدی هدف — دکمه‌های نقش هرگز برنمی‌گردند."""
        target = str(target_id).encode()
        # ۱) فقط دکمه‌های منوی رأی (پیشوند vote در کال‌بک)
        for button in self._vote_menu_buttons(message):
            parts = button.data.split(b"|")
            if any(part == target for part in parts[1:]):
                return button
        # ۲) فقط برای پیام‌های منوی اعدام — آخرین بخش کال‌بک آیدی هدف
        text = _compact(getattr(message, "raw_text", ""))
        if any(part in text for part in ASK_LYNCH_PARTS):
            for row in message.buttons or []:
                for button in row:
                    data = getattr(button, "data", None)
                    if not data:
                        continue
                    parts = data.split(b"|")
                    if parts and parts[-1] == target:
                        return button
        return None

    def _check_vote_confirmation(self, message, text):
        """اگر پیام جدید تأییدِ رأی در انتظار باشد، آزادش می‌کند."""
        if not self.vote_watchers:
            return
        confirmed = False
        if CHOICE_ACCEPTED in text:
            # توست دکمه یا پیام خصوصی «انتخاب پذیرفته شد»
            confirmed = True
        elif VOTE_ANNOUNCE_MARK in text and VOTE_ANNOUNCE_WORD in text:
            # اعلام عمومی: «X نظرش اینه که Y اعدام بشه»
            ids = set()
            for entity in getattr(message, "entities", None) or []:
                uid = getattr(entity, "user_id", None)
                if uid:
                    ids.add(uid)
            if self.owner_id and self.owner_id in ids:
                confirmed = True
            else:
                for watcher in self.vote_watchers:
                    if watcher["target_id"] in ids:
                        confirmed = True
                        break
                    name = watcher.get("target_name") or ""
                    if name and name in text:
                        confirmed = True
                        break
        if confirmed:
            for watcher in self.vote_watchers:
                watcher["event"].set()

    async def _click_vote(self, message, vote):
        """کلیک روی دکمهٔ رأی هدف + تأیید سه‌راهی.

        خروجی: (status, detail) که status یکی از
        ok / missing / timesup / fail است.
        """
        async with self.vote_lock:
            button = self._find_button(message, vote["id"])
            if button is None:
                return "missing", "بازیکن در فهرست رأی نیست"

            watcher = {
                "target_id": vote["id"],
                "target_name": vote.get("name", ""),
                "event": asyncio.Event(),
            }
            self.vote_watchers.append(watcher)
            try:
                last_error = "پاسخ تأیید دریافت نشد"
                for attempt in (1, 2):
                    if attempt == 2:
                        await asyncio.sleep(2.5)
                    answer_text = ""
                    try:
                        answer = await message.click(data=button.data)
                        answer_text = _compact(getattr(answer, "message", ""))
                    except Exception as exc:
                        last_error = str(exc)[:120]
                    if answer_text:
                        if CHOICE_ACCEPTED in answer_text:
                            return "ok", answer_text
                        if TIMES_UP in answer_text:
                            return "timesup", answer_text
                        if attempt == 2 and any(
                            m in answer_text for m in ALREADY_VOTED_MARKS
                        ):
                            # تلاش اول احتمالاً ثبت شده و ربات می‌گوید
                            # «قبلاً رأی داده‌ای» → رأی ثبت است
                            return "ok", answer_text
                        last_error = answer_text
                    # توست قطعی نبود؛ منتظر اعلام گروه یا پیام خصوصی
                    try:
                        await asyncio.wait_for(
                            watcher["event"].wait(),
                            timeout=VOTE_CONFIRM_TIMEOUT,
                        )
                        return "ok", "با اعلام ربات تأیید شد"
                    except asyncio.TimeoutError:
                        pass
                return "fail", last_error
            finally:
                try:
                    self.vote_watchers.remove(watcher)
                except ValueError:
                    pass

    # ─────────────────────────────────────────
    # منوی رأی اعدام
    # ─────────────────────────────────────────

    async def _handle_lynch_prompt(self, message):
        if not self.is_vote_enabled():
            return
        # بدون دکمهٔ کال‌بک، منو نیست
        if not any(
            getattr(b, "data", None)
            for row in (message.buttons or [])
            for b in row
        ):
            return
        state = self._state_for_prompt(message)
        if not state:
            return

        prompt_id = getattr(message, "id", None)

        # جلوگیری از پردازش دوبارهٔ همان منو (ویرایش شمارش معکوس و...)
        now = time.monotonic()
        if state.get("last_prompt_id") == prompt_id:
            elapsed = now - state.get("last_prompt_ts", 0.0)
            pending_trouble = (
                state.get("trouble_mode")
                and state.get("trouble_prompts", 0) < 2
            )
            # راند دوم دردسر می‌تواند همان پیام را ویرایش کند؛ با فاصلهٔ
            # حداقلی اجازهٔ پردازش دوباره می‌دهد
            if pending_trouble:
                if elapsed < TROUBLE_ROUND_GAP:
                    return
            elif elapsed < PROMPT_DEDUP_SECONDS:
                return
        state["last_prompt_id"] = prompt_id
        state["last_prompt_ts"] = now

        # ─── راندهای دردسر ───
        if state.get("trouble_mode") and state.get("trouble_prompts", 0) < 2:
            await self._handle_trouble_prompt(state, message, prompt_id)
            return

        state["trouble_mode"] = False

        # ─── فاز عادی ───
        if not state["normal_votes"]:
            await self._quick_notice(
                state["group_id"], "🗳 رأی ذخیره‌شده‌ای ندارید."
            )
            return

        vote = state["normal_votes"][0]
        state["current_attempt"] = {
            "kind": "normal",
            "vote": vote,
            "prompt_id": prompt_id,
        }
        status, detail = await self._click_vote(message, vote)
        state["current_attempt"] = None

        if status == "ok":
            used = state["normal_votes"].popleft()
            self._save_games()
            await self._quick_notice(
                state["group_id"],
                "✅ رأی شب برای %s ثبت و از صف حذف شد." % used["name"],
            )
            return
        if status == "missing":
            used = state["normal_votes"].popleft()
            self._save_games()
            await self._quick_notice(
                state["group_id"],
                "❌ %s در فهرست زنده‌ها نیست؛ رأی این شب حذف شد." % used["name"],
            )
            return
        if status == "timesup":
            state["normal_votes"].popleft()
            self._save_games()
            await self._quick_notice(
                state["group_id"],
                "⏰ وقت تمام شد؛ رأی این شب کنسل و حذف شد.",
            )
            return
        await self._quick_notice(
            state["group_id"],
            "❌ رأی ثبت نشد: %s\n(رأی در صف ماند)" % detail,
        )

    async def _handle_trouble_prompt(self, state, message, prompt_id):
        """راند دردسر — رأی درد ۱ در راند اول و رأی درد ۲ در راند دوم."""
        state["trouble_prompts"] += 1
        round_no = state["trouble_prompts"]
        idx = round_no - 1
        vote = state["trouble_votes"][idx]
        if vote is None:
            for i in (0, 1):
                if state["trouble_votes"][i] is not None:
                    idx, vote = i, state["trouble_votes"][i]
                    break

        if vote is None:
            # رأی دردی ذخیره نشده → منتظر دستور سریع دستی
            state["waiting_trouble_prompt"] = message
            state["current_attempt"] = None
            self._save_games()
            await self._quick_notice(
                state["group_id"],
                "🤯 راند دردسر %d! رأی دردی ذخیره نشده.\n"
                "سریع `رای درد %d @هدف` یا `رای درد %d` + ریپلای بدهید." % (
                    round_no, round_no, round_no,
                ),
            )
            return

        state["trouble_votes"][idx] = None
        state["current_attempt"] = {
            "kind": "trouble",
            "vote": vote,
            "slot": idx,
            "prompt_id": prompt_id,
        }
        self._save_games()
        status, detail = await self._click_vote(message, vote)
        state["current_attempt"] = None

        if status == "ok":
            if state["trouble_prompts"] >= 2:
                state["trouble_mode"] = False
            self._save_games()
            await self._quick_notice(
                state["group_id"],
                "🤯 رأی درد %d برای %s ثبت و حذف شد ✅" % (idx + 1, vote["name"]),
            )
            return
        if status == "missing":
            if state["trouble_prompts"] >= 2:
                state["trouble_mode"] = False
            self._save_games()
            await self._quick_notice(
                state["group_id"],
                "❌ %s در فهرست زنده‌ها نیست؛ رأی درد %d حذف شد." % (
                    vote["name"], idx + 1,
                ),
            )
            return
        if status == "timesup":
            state["trouble_mode"] = False
            self._save_games()
            await self._quick_notice(
                state["group_id"],
                "⏰ وقت تمام شد؛ رأی درد این راند کنسل و حذف شد.",
            )
            return
        # خطای موقت → رأی به اسلات برگردد
        state["trouble_votes"][idx] = vote
        self._save_games()
        await self._quick_notice(
            state["group_id"],
            "❌ رأی درد %d ثبت نشد: %s\n(در اسلات ماند)" % (idx + 1, detail),
        )

    async def _cancel_night_vote(self, state, reason, keep_trouble=False):
        """پایان شب / لغو رأی‌گیری → رأیِ همان شب به‌کل کنسل می‌شود.

        keep_trouble=True فقط برای «وقت تموم شد» بین دو راند دردسر؛
        راند بعدی همان روز همچنان منتظر می‌ماند.
        """
        attempt = state.get("current_attempt")
        state["current_attempt"] = None
        state["waiting_trouble_prompt"] = None
        if not keep_trouble:
            state["trouble_mode"] = False
            state["trouble_prompts"] = 0
        removed = False
        if attempt:
            if attempt.get("kind") == "normal" and state["normal_votes"]:
                front = state["normal_votes"][0]
                if front and front["id"] == attempt["vote"]["id"]:
                    state["normal_votes"].popleft()
                    removed = True
            elif attempt.get("kind") == "trouble":
                slot = attempt.get("slot")
                if slot is not None and 0 <= slot < 2:
                    state["trouble_votes"][slot] = None
                    removed = True
        self._save_games()
        if removed:
            await self._quick_notice(state["group_id"], "🗑 %s" % reason)

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

    async def _owner_notice(self, text):
        """پیام نتیجه به Saved Messages خود کاربر."""
        try:
            await self.client.send_message("me", text)
        except Exception:
            pass

    # ─────────────────────────────────────────
    # وضعیت روستا
    # ─────────────────────────────────────────

    def get_village_status(self, group_id):
        state = self._state(group_id)
        if not state or not state["owner_joined"] or not state["player_count"]:
            return "❌ هنوز حضور شما شناسایی نشده."
        count = state["player_count"]
        wolves = min(max(count // 5, 1), 5)
        max_negative = (count - 1) // 2
        min_village = count - max_negative
        max_village = count - wolves
        mode = {"normal": "معمولی", "chaos": "آشوب", "unknown": "نامشخص"}[state["mode"]]

        phase_text = ""
        if state.get("phase"):
            label = "روز ☀️" if state["phase"] == "day" else "شب 🌙"
            phase_text = "\n📅 الان: %s %d" % (label, state.get("day_number") or 1)
        alive = ""
        if state["alive_count"]:
            alive = "\n🙂 بازیکنان زنده: %d" % state["alive_count"]

        # نمایش رأی‌های ذخیره‌شده
        vote_lines = ""
        if state["normal_votes"]:
            vote_lines += "\n\n🗳 **رأی‌های ذخیره‌شده:**\n"
            for i, v in enumerate(state["normal_votes"], 1):
                vote_lines += "  `%d` → %s\n" % (i, v["name"])
        for i, tv in enumerate(state["trouble_votes"], 1):
            if tv:
                if not vote_lines:
                    vote_lines = "\n"
                vote_lines += "🤯 درد `%d` → %s\n" % (i, tv["name"])

        return (
            "🐺 **وضعیت احتمالی روستا**\n\n"
            "🎮 مود: %s\n"
            "👥 بازیکنان شروع: %d%s%s\n"
            "🐺 گرگ‌های اولیه: حدود %d\n"
            "🔴 منفی/مستقل: بین %d تا %d\n"
            "🟢 روستایی: بین %d تا %d%s\n\n"
            "ترکیب دقیق مخفی است." % (
                mode, count, alive, phase_text, wolves,
                wolves, max_negative, min_village, max_village, vote_lines,
            )
        )

    # ─────────────────────────────────────────
    # انتظار بازی بعدی و جوین خودکار (نکست)
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
        return any(m in text for m in NEXT_NOTIFY_MARKS)

    def _schedule_auto_join(self, notification):
        """شروع ورود خودکار بعد از اطلاعیهٔ بازی جدید در پیوی."""
        key = ("notify", getattr(notification, "id", id(notification)))
        task = self.next_join_tasks.get(key)
        if task and not task.done():
            return
        try:
            self.next_join_tasks[key] = asyncio.create_task(
                self._auto_join_next_game(notification)
            )
        except RuntimeError:
            pass

    def _schedule_join_group(self, group_id, token):
        """شروع ورود خودکار با توکن دکمهٔ «وارید شوید» داخل خود گروه."""
        key = ("join", int(group_id), token)
        task = self.join_tasks.get(key)
        if task and not task.done():
            return
        try:
            self.join_tasks[key] = asyncio.create_task(
                self._join_group_game(group_id, token)
            )
        except RuntimeError:
            pass

    async def _auto_join_next_game(self, notification):
        async with self.next_join_lock:
            group = await self._group_from_notification(notification)
            if group is None and len(self.next_group_ids) == 1:
                try:
                    group = await self.client.get_entity(
                        next(iter(self.next_group_ids))
                    )
                except Exception:
                    group = None
            if group is None:
                await self._owner_notice(
                    "❌ نکست: گروه بازی جدید پیدا نشد؛ انتظار لغو شد."
                )
                self.clear_next_wait()
                return
            group_id = int(getattr(group, "id", group))

            # پیدا کردن دکمهٔ «وارید شوید» پیام استارت (گیف)
            token = None
            for _ in range(JOIN_SCAN_ROUNDS):
                try:
                    messages = await self.client.get_messages(group, limit=30)
                    for message in messages:  # جدیدترین اول
                        if getattr(message, "sender_id", None) not in WEREWOLF_BOT_IDS:
                            continue
                        token = self._join_token_from_message(message)
                        if token:
                            break
                    if token:
                        break
                except Exception:
                    pass
                await asyncio.sleep(2)

            if not token:
                await self._owner_notice(
                    "❌ نکست: دکمهٔ «وارید شوید» بازی جدید پیدا نشد."
                )
                return

            await self._do_join(group_id, token)

    async def _join_group_game(self, group_id, token):
        async with self.next_join_lock:
            await self._do_join(int(group_id), token)

    async def _do_join(self, group_id, token):
        """استارت بازی با لینک join و انتظار ۱۰ ثانیه‌ای برای تأیید ورود.

        اگر پیام «شما با موفقیت وارد بازی ... شدید» تا ۱۰ ثانیه نیاید،
        دوباره با همان لینک استارت می‌کند (حداکثر ۳ بار).
        """
        joined = False
        for attempt in range(1, JOIN_ATTEMPTS + 1):
            self.join_confirm = asyncio.Event()
            try:
                await self.client.send_message(
                    WEREWOLF_BOT_ID, "/start join%s" % token
                )
            except Exception as exc:
                self.join_confirm = None
                await self._owner_notice(
                    "❌ نکست: ارسال استارت بازی ناموفق بود: %s" % str(exc)[:80]
                )
                return
            try:
                await asyncio.wait_for(
                    self.join_confirm.wait(), timeout=JOIN_CONFIRM_TIMEOUT
                )
                joined = True
                break
            except asyncio.TimeoutError:
                continue
        self.join_confirm = None

        if not joined:
            self.clear_next_wait(group_id)
            await self._owner_notice(
                "❌ نکست: بعد از %d بار استارت، پیام «وارد بازی شدید» "
                "دریافت نشد؛ انتظار لغو شد." % JOIN_ATTEMPTS
            )
            return

        state = self._state(group_id, create=True, manual=True)
        state["owner_joined"] = True
        state["enabled"] = True
        state["join_token"] = token
        self._save_games()
        self.clear_next_wait(group_id)
        await self._quick_notice(group_id, "✅ وارد بازی شدم!", 6)

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
