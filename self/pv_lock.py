"""
ماژول قفل پیوی - حذف دوطرفه خودکار پیام‌های کاربر قفل‌شده
وقتی یک کاربر قفل پیوی شود، هر پیامی که در چت خصوصی ارسال کند
در کسری از ثانیه برای هر دو طرف حذف می‌شود (revoke=True)
"""

import asyncio
import time


def _safe_name(name):
    """حذف کاراکترهای مشکل‌ساز مارک‌داون از اسم"""
    if not name:
        return "نامشخص"
    for ch in ('*', '_', '`', '[', ']', '~'):
        name = name.replace(ch, '')
    return name.strip() or "نامشخص"


class PVLockManager:
    def __init__(self, client, config_manager):
        self.client = client
        self.config = config_manager
        # آمار حذف‌ها (در حافظه - نیازی به ذخیره نیست)
        self.delete_count = {}
        self._last_error_log = {}
        self._errors = {}
        self._lock = asyncio.Lock()

    # ═══════════════════════════════════════
    # مدیریت لیست
    # ═══════════════════════════════════════

    def _get_locks(self):
        return self.config.get("pv_locks", [])

    def _save_locks(self, locks):
        self.config.set("pv_locks", locks)

    def is_locked(self, user_id):
        """بررسی قفل بودن کاربر"""
        if not user_id:
            return False
        for lock in self._get_locks():
            if lock["user_id"] == user_id:
                return True
        return False

    def find_lock(self, user_id):
        for lock in self._get_locks():
            if lock["user_id"] == user_id:
                return lock
        return None

    # ═══════════════════════════════════════
    # قفل کردن
    # ═══════════════════════════════════════

    def add_lock(self, user_id, user_name="", username=""):
        """قفل پیوی کاربر - برمیگرداند متن نتیجه"""
        user_name = _safe_name(user_name) or str(user_id)
        locks = self._get_locks()

        for lock in locks:
            if lock["user_id"] == user_id:
                lock["user_name"] = user_name
                if username:
                    lock["username"] = username
                lock["locked_at"] = time.time()
                self._save_locks(locks)
                return (
                    f"⚠️ **قبلاً قفل شده بود - بروزرسانی شد**\n\n"
                    f"  ▸ کاربر: **{user_name}**\n"
                    f"  ▸ آیدی: `{user_id}`"
                )

        locks.append({
            "user_id": user_id,
            "user_name": user_name,
            "username": username or "",
            "locked_at": time.time(),
            "deleted_messages": 0,
        })
        self._save_locks(locks)

        return (
            "🔒 **پیوی قفل شد**\n\n"
            f"  ▸ کاربر: **{user_name}**\n"
            f"  ▸ آیدی: `{user_id}`\n\n"
            "از این لحظه هر پیامی که در پیوی ارسال کند\n"
            "بلافاصله برای هر دو طرف حذف می‌شود 🗑"
        )

    # ═══════════════════════════════════════
    # حذف قفل
    # ═══════════════════════════════════════

    def remove_lock(self, user_id):
        """حذف قفل با آیدی کاربر"""
        locks = self._get_locks()
        new_locks = [l for l in locks if l["user_id"] != user_id]

        if len(new_locks) == len(locks):
            return f"❌ کاربر `{user_id}` در لیست قفل پیوی نیست"

        removed = None
        for l in locks:
            if l["user_id"] == user_id:
                removed = l
                break

        self._save_locks(new_locks)
        name = _safe_name((removed or {}).get("user_name", "")) or str(user_id)
        deleted = (removed or {}).get("deleted_messages", 0)

        return (
            "🔓 **قفل پیوی حذف شد**\n\n"
            f"  ▸ کاربر: **{name}**\n"
            f"  ▸ آیدی: `{user_id}`\n"
            f"  ▸ پیام‌های حذف شده: `{deleted}`"
        )

    def remove_by_index(self, index):
        """حذف قفل با شماره در لیست"""
        locks = self._get_locks()
        if not locks:
            return "📭 لیست قفل پیوی خالی است"
        if index < 1 or index > len(locks):
            return f"❌ شماره نامعتبر! (بین 1 تا {len(locks)})"

        removed = locks.pop(index - 1)
        self._save_locks(locks)
        name = _safe_name(removed.get("user_name", "")) or str(removed["user_id"])
        return f"🔓 قفل پیوی **{name}** حذف شد"

    def clear_all(self):
        """حذف همه قفل‌ها"""
        count = len(self._get_locks())
        self._save_locks([])
        self.delete_count.clear()
        if count == 0:
            return "📭 لیست قفل پیوی خالی بود"
        return f"🗑 قفل پیوی **{count}** کاربر حذف شد"

    # ═══════════════════════════════════════
    # لیست
    # ═══════════════════════════════════════

    def get_list_text(self):
        locks = self._get_locks()

        if not locks:
            return (
                "📭 **لیست قفل پیوی خالی است**\n\n"
                "**روش‌های قفل کردن:**\n"
                "▸ در پیوی فرد: `قفل پیوی`\n"
                "▸ ریپلای + `قفل پیوی`\n"
                "▸ `قفل پیوی @username`\n"
                "▸ `قفل پیوی [آیدی عددی]`"
            )

        text = f"🔒 **لیست قفل پیوی:** `{len(locks)}` کاربر\n\n"

        for i, lock in enumerate(locks, 1):
            name = _safe_name(lock.get("user_name", "")) or str(lock["user_id"])
            username = lock.get("username", "")
            deleted = lock.get("deleted_messages", 0)

            line = f"  🔒 `{i}` ▸ **{name}**"
            if username:
                line += f" (@{username})"
            text += line + "\n"
            text += f"       آیدی: `{lock['user_id']}`"
            if deleted:
                text += f" | حذف شده: `{deleted}`"
            text += "\n\n"

        text += (
            "**دستورات حذف:**\n"
            "`حذف پیوی قفل` + ریپلای\n"
            "`حذف پیوی قفل @username`\n"
            "`حذف پیوی قفل [آیدی عددی]`\n"
            "`حذف قفل پیوی [شماره]` ← شماره لیست\n"
            "`پاکسازی قفل پیوی` ← حذف همه"
        )
        return text

    def get_status_text(self):
        """متن وضعیت خلاصه برای پنل"""
        locks = self._get_locks()
        total_deleted = sum(l.get("deleted_messages", 0) for l in locks)
        return (
            "🔒 **قفل پیوی**\n\n"
            f"  ▸ کاربران قفل شده: `{len(locks)}`\n"
            f"  ▸ کل پیام‌های حذف شده: `{total_deleted}`\n\n"
            "**قفل کردن:**\n"
            "▸ پیوی + `قفل پیوی` یا `پیوی قفل`\n"
            "▸ ریپلای + `قفل پیوی`\n"
            "▸ `قفل پیوی @username`\n"
            "▸ `قفل پیوی [آیدی]`\n\n"
            "**حذف قفل:**\n"
            "▸ `حذف پیوی قفل` / `حذف قفل پیوی`\n"
            "▸ `لیست قفل پیوی` | `پاکسازی قفل پیوی`"
        )

    # ═══════════════════════════════════════
    # هندلر پیام‌های ورودی - حذف فوری دوطرفه
    # ═══════════════════════════════════════

    async def handle_new_message(self, event):
        """
        بررسی پیام ورودی - اگر فرستنده قفل باشد
        پیام بلافاصله برای هر دو طرف حذف می‌شود
        برمی‌گرداند: True اگر پیام حذف شد
        """
        # فقط چت‌های خصوصی
        try:
            if not event.is_private:
                return False
        except Exception:
            return False

        locks = self._get_locks()
        if not locks:
            return False

        sender_id = event.sender_id
        if not sender_id or not self.is_locked(sender_id):
            return False

        try:
            # revoke=True → حذف برای هر دو طرف
            await self.client.delete_messages(
                event.chat_id,
                [event.message.id],
                revoke=True
            )

            # بروزرسانی شمارنده
            for lock in locks:
                if lock["user_id"] == sender_id:
                    lock["deleted_messages"] = lock.get("deleted_messages", 0) + 1
                    break
            self._save_locks(locks)

            print(f"🔒 قفل پیوی: پیام کاربر {sender_id} حذف شد")
            return True

        except Exception as e:
            error_key = f"{sender_id}:{type(e).__name__}"
            last_log = self._last_error_log.get(error_key, 0)
            now = time.time()
            # لاگ خطا حداکثر هر 60 ثانیه یکبار برای هر کاربر
            if now - last_log > 60:
                self._last_error_log[error_key] = now
                print(f"⚠️ خطا در حذف پیام قفل پیوی ({sender_id}): {str(e)[:80]}")
            return False
