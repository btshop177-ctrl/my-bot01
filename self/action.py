"""
ماژول اکشن - ارسال مداوم وضعیت (تایپ، ویس، ویدیو و ...) در چت‌ها
هر چت اکشن مجزا دارد - مداوم و بدون توقف
نسخه نهایی: رفع Race Condition + مدیریت خطا + حذف صحیح
"""

import asyncio
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import (
    SendMessageTypingAction,
    SendMessageRecordAudioAction,
    SendMessageChooseStickerAction,
    SendMessageChooseContactAction,
    SendMessageRecordRoundAction,
    SendMessageUploadVideoAction,
    SendMessageUploadPhotoAction,
    SendMessageUploadDocumentAction,
    SendMessageGamePlayAction,
    SendMessageCancelAction,
)


ACTION_MAP = {
    "تایپ": SendMessageTypingAction,
    "ویس": SendMessageRecordAudioAction,
    "استیکر": SendMessageChooseStickerAction,
    "مخاطب": SendMessageChooseContactAction,
    "ویدیو گرد": SendMessageRecordRoundAction,
    "آپلود ویدیو": SendMessageUploadVideoAction,
    "آپلود عکس": SendMessageUploadPhotoAction,
    "آپلود فایل": SendMessageUploadDocumentAction,
    "بازی": SendMessageGamePlayAction,
}

ACTION_DESC = {
    "تایپ": "در حال تایپ کردن...",
    "ویس": "در حال ضبط صدا...",
    "استیکر": "در حال انتخاب استیکر...",
    "مخاطب": "در حال انتخاب مخاطب...",
    "ویدیو گرد": "در حال ضبط ویدیو گرد...",
    "آپلود ویدیو": "در حال آپلود ویدیو...",
    "آپلود عکس": "در حال آپلود عکس...",
    "آپلود فایل": "در حال آپلود فایل...",
    "بازی": "در حال بازی...",
}

ACTION_SCOPE_ALL = "all"
ACTION_SCOPE_GROUPS = "groups"
ACTION_SCOPE_CUSTOM = "custom"


def _safe_name(name):
    """حذف کاراکترهای مشکل‌ساز مارک‌داون از اسم"""
    if not name:
        return "نامشخص"
    for ch in ('*', '_', '`', '[', ']', '~'):
        name = name.replace(ch, '')
    return name.strip() or "نامشخص"


class ActionManager:
    def __init__(self, client, config_manager):
        self.client = client
        self.config = config_manager
        self.tasks = {}

    # ═══════════════════════════════════════
    # مدیریت لیست اکشن‌ها
    # ═══════════════════════════════════════

    def _get_actions(self):
        return self.config.get("actions_list", [])

    def _save_actions(self, actions):
        self.config.set("actions_list", actions)

    def _find_action(self, chat_id):
        actions = self._get_actions()
        for a in actions:
            if a["chat_id"] == chat_id:
                return a
        return None

    # ═══════════════════════════════════════
    # افزودن اکشن به چت
    # ═══════════════════════════════════════

    def add_action(self, chat_id, action_type, chat_name=""):
        if action_type not in ACTION_MAP:
            names = " | ".join(ACTION_MAP.keys())
            return f"❌ نوع نامعتبر\n\nانواع: `{names}`"

        chat_name = _safe_name(chat_name)
        actions = self._get_actions()

        for a in actions:
            if a["chat_id"] == chat_id:
                old_type = a["action_type"]
                a["action_type"] = action_type
                a["chat_name"] = chat_name
                a["enabled"] = True
                self._save_actions(actions)

                self._stop_task(chat_id)
                self._start_task(chat_id, action_type)

                desc = ACTION_DESC.get(action_type, "")
                return (
                    f"✅ اکشن بروزرسانی شد\n\n"
                    f"  ▸ چت: {chat_name}\n"
                    f"  ▸ قبلی: `{old_type}`\n"
                    f"  ▸ جدید: {action_type} → {desc}"
                )

        actions.append({
            "chat_id": chat_id,
            "chat_name": chat_name,
            "action_type": action_type,
            "enabled": True,
        })
        self._save_actions(actions)

        self._start_task(chat_id, action_type)

        desc = ACTION_DESC.get(action_type, "")
        return (
            f"✅ اکشن فعال شد\n\n"
            f"  ▸ چت: {chat_name}\n"
            f"  ▸ نوع: {action_type} → {desc}"
        )

    # ═══════════════════════════════════════
    # روشن / خاموش کردن
    # ═══════════════════════════════════════

    def enable_action(self, chat_id):
        actions = self._get_actions()
        for a in actions:
            if a["chat_id"] == chat_id:
                if a.get("enabled", True):
                    return "⚠️ اکشن قبلاً روشن است"
                a["enabled"] = True
                self._save_actions(actions)
                self._start_task(chat_id, a["action_type"])
                name = _safe_name(a.get("chat_name", ""))
                return f"✅ اکشن روشن شد → {name} ({a['action_type']})"
        return "❌ اکشنی برای این چت ثبت نشده\nابتدا: `اکشن [نوع]`"

    def disable_action(self, chat_id):
        actions = self._get_actions()
        for a in actions:
            if a["chat_id"] == chat_id:
                if not a.get("enabled", True):
                    return "⚠️ اکشن قبلاً خاموش است"
                a["enabled"] = False
                self._save_actions(actions)
                self._stop_task(chat_id)
                name = _safe_name(a.get("chat_name", ""))
                return f"🔴 اکشن خاموش شد → {name}"
        return "❌ اکشنی برای این چت ثبت نشده"

    # ═══════════════════════════════════════
    # حذف اکشن
    # ═══════════════════════════════════════

    def remove_action(self, chat_id):
        actions = self._get_actions()
        new_actions = [a for a in actions if a["chat_id"] != chat_id]

        if len(new_actions) == len(actions):
            return "❌ اکشنی برای این چت ثبت نشده"

        self._stop_task(chat_id)
        self._save_actions(new_actions)
        return "✅ اکشن حذف شد"

    def remove_by_index(self, index):
        actions = self._get_actions()
        if not actions:
            return "📭 هیچ اکشنی ثبت نشده"
        if index < 1 or index > len(actions):
            return f"❌ شماره نامعتبر! (بین 1 تا {len(actions)})"

        removed = actions.pop(index - 1)
        self._stop_task(removed["chat_id"])
        self._save_actions(actions)

        name = _safe_name(removed.get("chat_name", "")) or str(removed["chat_id"])
        return f"✅ اکشن {name} حذف شد"

    def remove_by_chat_id(self, chat_id):
        """حذف اکشن با آیدی چت"""
        return self.remove_action(chat_id)

    def clear_all(self):
        self.stop_all_tasks()
        self._save_actions([])
        return "🗑 همه اکشن‌ها حذف شدند"

    # ═══════════════════════════════════════
    # لیست
    # ═══════════════════════════════════════

    def get_list_text(self):
        actions = self._get_actions()

        if not actions:
            return (
                "📭 هیچ اکشنی ثبت نشده\n\n"
                "برای فعال‌سازی:\n"
                "`اکشن [نوع]` → در چت مورد نظر\n"
                "مثال: `اکشن تایپ`"
            )

        text = f"⚡ لیست اکشن‌ها: `{len(actions)}`\n\n"

        for i, a in enumerate(actions, 1):
            status = "🟢" if a.get("enabled", True) else "🔴"
            name = _safe_name(a.get("chat_name", "")) or str(a["chat_id"])
            action_type = a.get("action_type", "تایپ")
            desc = ACTION_DESC.get(action_type, "")
            running = "▶️" if a["chat_id"] in self.tasks else "⏸"

            text += (
                f"  {status} `{i}` ▸ {name}\n"
                f"       {running} {action_type} → {desc}\n"
                f"       آیدی: `{a['chat_id']}`\n\n"
            )

        text += (
            "دستورات:\n"
            "`اکشن [نوع]` → فعال‌سازی در چت فعلی\n"
            "`اکشن روشن` / `اکشن خاموش`\n"
            "`حذف اکشن` → حذف اکشن چت فعلی\n"
            "`حذف اکشن [شماره]`\n"
            "`پاکسازی اکشن` → حذف همه\n"
            "`لیست اکشن`"
        )
        return text

    def get_status_text(self):
        actions = self._get_actions()
        enabled_count = sum(1 for a in actions if a.get("enabled", True))
        running_count = len(self.tasks)

        text = "⚡ مدیریت اکشن\n\n"
        text += f"  ▸ کل اکشن‌ها: `{len(actions)}`\n"
        text += f"  ▸ فعال: `{enabled_count}`\n"
        text += f"  ▸ در حال اجرا: `{running_count}`\n\n"

        if actions:
            text += "اکشن‌های ثبت شده:\n"
            for i, a in enumerate(actions, 1):
                status = "🟢" if a.get("enabled", True) else "🔴"
                name = _safe_name(a.get("chat_name", "")) or str(a["chat_id"])
                atype = a.get("action_type", "تایپ")
                text += f"  {status} `{i}` {name} → `{atype}`\n"
            text += "\n"

        text += "انواع اکشن:\n"
        for name, desc in ACTION_DESC.items():
            text += f"  ▹ `{name}` → {desc}\n"

        text += (
            "\nدستورات:\n"
            "`اکشن [نوع]` → در چت مورد نظر\n"
            "`اکشن روشن/خاموش` → این چت\n"
            "`حذف اکشن` | `حذف اکشن [شماره]`\n"
            "`لیست اکشن` | `پاکسازی اکشن`\n\n"
            "مثال: در گروه بنویسید `اکشن تایپ`"
        )
        return text

    # ═══════════════════════════════════════
    # مدیریت Task ها
    # ═══════════════════════════════════════

    def _start_task(self, chat_id, action_type):
        """شروع task - ابتدا قبلی متوقف می‌شود"""
        self._stop_task(chat_id)

        action_class = ACTION_MAP.get(action_type, SendMessageTypingAction)
        task = asyncio.ensure_future(
            self._action_loop(chat_id, action_class, action_type)
        )
        self.tasks[chat_id] = task
        print(f"⚡ اکشن شروع شد: {chat_id} → {action_type}")

    def _stop_task(self, chat_id):
        """توقف task - حذف امن از دیکشنری"""
        task = self.tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
            print(f"⚡ اکشن متوقف شد: {chat_id}")

    def stop_all_tasks(self):
        """توقف همه task ها"""
        for chat_id in list(self.tasks.keys()):
            task = self.tasks.pop(chat_id, None)
            if task and not task.done():
                task.cancel()
        self.tasks.clear()
        print("⚡ همه اکشن‌ها متوقف شدند")

    def start_saved_actions(self):
        """شروع اکشن‌های ذخیره شده (بعد از ریستارت)"""
        actions = self._get_actions()
        count = 0
        for a in actions:
            if a.get("enabled", True):
                self._start_task(a["chat_id"], a.get("action_type", "تایپ"))
                count += 1
        if count > 0:
            print(f"⚡ {count} اکشن از تنظیمات قبلی شروع شد")

    async def _action_loop(self, chat_id, action_class, action_type):
        """حلقه مداوم ارسال اکشن"""
        error_count = 0
        max_errors = 10
        current_task = asyncio.current_task()

        try:
            while True:
                # اگر task جدیدی جایگزین شده، خارج شو
                if self.tasks.get(chat_id) is not current_task:
                    break

                action_data = self._find_action(chat_id)
                if not action_data or not action_data.get("enabled", True):
                    break

                try:
                    await self.client(SetTypingRequest(
                        peer=chat_id,
                        action=action_class()
                    ))
                    error_count = 0

                except Exception as e:
                    error = str(e).upper()
                    error_str = str(e)
                    error_count += 1

                    if "FLOOD" in error or "WAIT" in error:
                        print(f"⏳ اکشن {chat_id}: Flood wait")
                        await asyncio.sleep(15)

                    elif ("FORBIDDEN" in error
                          or "BANNED" in error
                          or "PEER_ID_INVALID" in error
                          or "COULD NOT FIND THE INPUT ENTITY" in error
                          or "INPUT ENTITY" in error):
                        name = _safe_name(
                            (action_data or {}).get("chat_name", "")
                        )
                        print(
                            f"❌ اکشن {chat_id} ({name}): "
                            f"چت نامعتبر - غیرفعال شد"
                        )
                        actions = self._get_actions()
                        for a in actions:
                            if a["chat_id"] == chat_id:
                                a["enabled"] = False
                                break
                        self._save_actions(actions)
                        break

                    elif error_count >= max_errors:
                        print(
                            f"❌ اکشن {chat_id}: "
                            f"خطاهای متوالی ({error_count})"
                        )
                        await asyncio.sleep(30)
                        error_count = 0

                    else:
                        print(f"⚠️ اکشن {chat_id}: {error_str[:60]}")

                await asyncio.sleep(4.5)

        except asyncio.CancelledError:
            pass

        finally:
            # فقط اگر همین task هنوز ثبت‌شده باشد حذفش کن
            if self.tasks.get(chat_id) is current_task:
                self.tasks.pop(chat_id, None)

            try:
                await self.client(SetTypingRequest(
                    peer=chat_id,
                    action=SendMessageCancelAction()
                ))
            except:
                pass