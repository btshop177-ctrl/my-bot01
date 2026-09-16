"""
ماژول دیتابیس کاربران - مدیریت چندکاربره سلف‌بات
ذخیره‌سازی JSON: اطلاعات API، سشن، کانفیگ، وضعیت و اعتبار زمانی هر کاربر
"""

import json
import os
import time
import shutil


SELF_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SELF_DIR, "data")
SESSIONS_DIR = os.path.join(SELF_DIR, "sessions")
DB_FILE = os.path.join(DATA_DIR, "users.json")


def default_user_config():
    """قالب پیش‌فرض config.json برای هر کاربر (هماهنگ با ConfigManager)"""
    return {
        "clock_enabled": False,
        "clock_bio_enabled": False,
        "bio_text": "",
        "clock_font": 9,
        "user_reactions": [],
        "chat_reactions": [],
        "text_reactions": [],
        "tapchi_enabled": False,
        "banner_mode": "forward",
        "banners": {},
        "active_effects": [],
        "open_panels": [],
        "owner_id": 0,
        "actions_list": [],
        "pv_locks": [],
    }


# وضعیت‌های کاربر
STATUS_NEW = "new"            # تازه /start کرده
STATUS_REGISTERED = "registered"  # API ID/HASH ثبت کرده
STATUS_PENDING = "pending"    # سشن ساخته - منتظر تایید ادمین
STATUS_ACTIVE = "active"      # فعال (سلف در حال اجرا)
STATUS_STOPPED = "stopped"    # توسط ادمین غیرفعال شده
STATUS_EXPIRED = "expired"    # اعتبارش تمام شده

STATUS_FA = {
    STATUS_NEW: "🆕 جدید",
    STATUS_REGISTERED: "📝 API ثبت شده",
    STATUS_PENDING: "⏳ در انتظار تایید",
    STATUS_ACTIVE: "🟢 فعال",
    STATUS_STOPPED: "🔴 غیرفعال",
    STATUS_EXPIRED: "⏰ منقضی شده",
}


class UsersDatabase:
    def __init__(self, admin_id):
        self.admin_id = int(admin_id) if admin_id else 0
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        self.data = self._load()
        self.ensure_admin()

    # ─── لود و ذخیره ───

    def _load(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data.setdefault("users", {})
                    return data
            except Exception as e:
                print(f"⚠️ خطا در خواندن دیتابیس: {e}")
        return {"admin_id": self.admin_id, "users": {}}

    def save(self):
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DB_FILE)

    # ─── ادمین: اولین کانفیگ و جیسون برای مدیر ───

    def ensure_admin(self):
        """
        تضمین وجود رکورد ادمین به عنوان اولین کاربر سیستم
        اگر فایل‌های قدیمی تک‌کاربره (config.json / user_session.session)
        وجود داشته باشند، به عنوان کانفیگ و سشن ادمین به ارث می‌رسند
        """
        self.data["admin_id"] = self.admin_id
        users = self.data.setdefault("users", {})

        if str(self.admin_id) in users:
            return

        # کانفیگ پیش‌فرض ادمین
        admin_dir = os.path.join(DATA_DIR, str(self.admin_id))
        os.makedirs(admin_dir, exist_ok=True)

        config_rel = f"data/{self.admin_id}/config.json"
        config_abs = os.path.join(SELF_DIR, config_rel)

        # به ارث بردن کانفیگ قدیمی تک‌کاربره (config.json)
        legacy_config = os.path.join(SELF_DIR, "config.json")
        if os.path.exists(legacy_config) and not os.path.exists(config_abs):
            try:
                shutil.copy2(legacy_config, config_abs)
                print(f"📦 کانفیگ قدیمی به عنوان کانفیگ ادمین منتقل شد")
            except Exception as e:
                print(f"⚠️ خطا در انتقال کانفیگ قدیمی: {e}")

        if not os.path.exists(config_abs):
            cfg = default_user_config()
            cfg["owner_id"] = self.admin_id
            with open(config_abs, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print(f"📝 اولین کانفیگ (config.json) برای مدیر ساخته شد")

        # به ارث بردن سشن قدیمی تک‌کاربره (user_session.session)
        session_rel = ""
        legacy_session = os.path.join(SELF_DIR, "user_session.session")
        if os.path.exists(legacy_session):
            session_rel = f"sessions/u{self.admin_id}"
            target = os.path.join(SELF_DIR, session_rel + ".session")
            if not os.path.exists(target):
                try:
                    shutil.copy2(legacy_session, target)
                    journal = legacy_session + "-journal"
                    if os.path.exists(journal):
                        shutil.copy2(journal, target + "-journal")
                    print(f"📦 سشن قدیمی به عنوان سشن ادمین منتقل شد")
                except Exception as e:
                    print(f"⚠️ خطا در انتقال سشن قدیمی: {e}")
                    session_rel = "user_session"
            else:
                session_rel = self._unique_session_name(self.admin_id)

        users[str(self.admin_id)] = {
            "telegram_id": self.admin_id,
            "name": "مدیر اصلی",
            "username": "",
            "api_id": None,
            "api_hash": None,
            "phone": "",
            "session": session_rel,
            "config": config_rel,
            "bot_token": None,
            "account_id": self.admin_id,
            "status": STATUS_ACTIVE if session_rel else STATUS_NEW,
            "created_at": time.time(),
            "activated_at": time.time() if session_rel else None,
            "expires_at": None,  # مدیر نامحدود
            "duration_days": None,
        }
        self.save()
        print(f"👑 رکورد مدیر اصلی ({self.admin_id}) آماده شد")

    # ─── ابزار نام یکتا برای سشن ───

    def _unique_session_name(self, tg_id):
        """
        ساخت نام سشن یکتا که قبلاً وجود نداشته باشد
        sessions/u<tg_id> → sessions/u<tg_id>_2 → ...
        """
        base = f"sessions/u{tg_id}"
        candidate = base
        counter = 2
        while os.path.exists(os.path.join(SELF_DIR, candidate + ".session")):
            candidate = f"{base}_{counter}"
            counter += 1
        return candidate

    # ─── کاربران ───

    def get_user(self, tg_id):
        return self.data["users"].get(str(tg_id))

    def upsert_user(self, tg_id, **fields):
        users = self.data["users"]
        key = str(tg_id)
        if key not in users:
            users[key] = {
                "telegram_id": int(tg_id),
                "name": "",
                "username": "",
                "api_id": None,
                "api_hash": None,
                "phone": "",
                "session": "",
                "config": "",
                "bot_token": None,
                "account_id": None,
                "status": STATUS_NEW,
                "created_at": time.time(),
                "activated_at": None,
                "expires_at": None,
                "duration_days": None,
            }
        users[key].update(fields)
        self.save()
        return users[key]

    def set_api(self, tg_id, api_id, api_hash):
        return self.upsert_user(
            tg_id, api_id=int(api_id), api_hash=api_hash,
            status=STATUS_REGISTERED
        )

    def set_session(self, tg_id, phone, account_id, name="", username=""):
        """ساخت سشن یکتا + config.json اختصاصی کاربر"""
        session_rel = self._unique_session_name(tg_id)

        user_dir = os.path.join(DATA_DIR, str(tg_id))
        os.makedirs(user_dir, exist_ok=True)

        config_rel = f"data/{tg_id}/config.json"
        config_abs = os.path.join(SELF_DIR, config_rel)
        if not os.path.exists(config_abs):
            cfg = default_user_config()
            cfg["owner_id"] = int(account_id)
            with open(config_abs, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

        return self.upsert_user(
            tg_id,
            phone=phone,
            account_id=int(account_id),
            session=session_rel,
            config=config_rel,
            name=name,
            username=username,
            status=STATUS_PENDING,
        )

    def activate(self, tg_id, days=None):
        """فعال‌سازی سلف کاربر; days=None یعنی نامحدود"""
        expires_at = None
        if days:
            expires_at = time.time() + int(days) * 86400
        return self.upsert_user(
            tg_id,
            status=STATUS_ACTIVE,
            activated_at=time.time(),
            expires_at=expires_at,
            duration_days=days,
        )

    def extend(self, tg_id, days):
        """تمدید اعتبار"""
        user = self.get_user(tg_id)
        if not user:
            return None
        base = user.get("expires_at") or time.time()
        if base < time.time():
            base = time.time()
        return self.upsert_user(
            tg_id,
            status=STATUS_ACTIVE,
            expires_at=base + int(days) * 86400,
        )

    def stop(self, tg_id):
        return self.upsert_user(tg_id, status=STATUS_STOPPED)

    def expire(self, tg_id):
        return self.upsert_user(tg_id, status=STATUS_EXPIRED)

    def delete_user(self, tg_id, remove_files=True):
        """حذف کامل کاربر + فایل‌هایش"""
        user = self.data["users"].pop(str(tg_id), None)
        self.save()

        if remove_files and user:
            session_rel = user.get("session", "")
            if session_rel:
                for suffix in (".session", ".session-journal"):
                    path = os.path.join(SELF_DIR, session_rel + suffix)
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass
            user_dir = os.path.join(DATA_DIR, str(tg_id))
            if os.path.isdir(user_dir):
                try:
                    shutil.rmtree(user_dir)
                except Exception:
                    pass
        return user

    def all_users(self):
        return list(self.data["users"].values())

    def pending_users(self):
        return [
            u for u in self.all_users() if u["status"] == STATUS_PENDING
        ]

    def active_users(self):
        return [
            u for u in self.all_users()
            if u["status"] == STATUS_ACTIVE and not self.is_expired(u)
        ]

    def is_expired(self, user):
        exp = user.get("expires_at")
        if not exp:
            return False
        return time.time() > exp

    def remaining_days(self, user):
        exp = user.get("expires_at")
        if not exp:
            return None  # نامحدود
        remaining = exp - time.time()
        if remaining <= 0:
            return 0
        return round(remaining / 86400, 1)
