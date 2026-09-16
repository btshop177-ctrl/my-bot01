"""
ماژول ساخت/دریافت خودکار اپ تلگرام از my.telegram.org
ورود با شماره + کد تایید (مثل ورود به سایت my.telegram.org)
اگر کاربر از قبل اپ داشته باشد، همان اطلاعات برگردانده می‌شود.

کارکرد این ماژول وابسته به ساختار صفحات my.telegram.org است؛
در صورت تغییر آن سایت ممکن است نیاز به به‌روزرسانی داشته باشد.
"""

import re

try:
    import requests
except ImportError:
    requests = None


class TGAppError(Exception):
    """خطای قابل نمایش به کاربر"""
    pass


BASE = "https://my.telegram.org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/auth",
    "Origin": BASE,
}


def _check_requests():
    if requests is None:
        raise TGAppError(
            "کتابخانه requests نصب نیست:\npip install requests"
        )


def _parse_alert(text):
    """خطاهای داخل صفحه را استخراج می‌کند"""
    m = re.search(
        r'<div[^>]*class="[^"]*alert[^"]*alert-error[^"]*"[^>]*>(.*?)</div>',
        text, re.S
    )
    if m:
        msg = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        msg = re.sub(r"\s+", " ", msg)
        if msg:
            return msg
    return None


class TelegramAppMaker:
    """جریان ساخت اپ برای یک کاربر (sync - با to_thread صدا بزنید)"""

    def __init__(self):
        _check_requests()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.random_hash = ""

    # ─── مرحله ۱: ارسال شماره و دریافت کد ───

    def send_password(self, phone):
        """
        شماره را می‌فرستد؛ کد تایید به تلگرام کاربر ارسال می‌شود.
        برمی‌گرداند: random_hash
        خطاها: TGAppError با پیام فارسی
        """
        try:
            r = self.session.post(
                f"{BASE}/auth/send_password",
                data={"phone": phone},
                timeout=30,
            )
        except requests.RequestException as e:
            raise TGAppError(f"خطای اتصال به my.telegram.org: {str(e)[:100]}")

        try:
            data = r.json()
        except ValueError:
            alert = _parse_alert(r.text)
            raise TGAppError(alert or f"پاسخ نامعتبر از سرور (کد {r.status_code})")

        if isinstance(data, dict):
            if data.get("random_hash"):
                self.random_hash = data["random_hash"]
                return self.random_hash
            # خطاهای شناخته‌شده
            err = data.get("error") or data.get("message") or ""
            if "FLOOD" in str(err).upper() or "Sorry, too many" in str(err):
                raise TGAppError(
                    "⏳ محدودیت تلگرام: تلاش‌های زیاد. چند ساعت دیگر دوباره امتحان کنید."
                )
            if "PHONE_NUMBER_INVALID" in str(err).upper():
                raise TGAppError("❌ شماره تلفن نامعتبر است.")
            raise TGAppError(err or "خطای ناشناخته در ارسال کد")

        raise TGAppError("پاسخ نامعتبر از سرور")

    # ─── مرحله ۲: تایید کد (ورود) ───

    def login(self, phone, code):
        """کد تایید را می‌فرستد و وارد my.telegram.org می‌شود"""
        if not self.random_hash:
            raise TGAppError("نشست نامعتبر است؛ دوباره شروع کنید")

        try:
            r = self.session.post(
                f"{BASE}/auth/login",
                data={
                    "phone": phone,
                    "random_hash": self.random_hash,
                    "password": code,
                },
                timeout=30,
            )
        except requests.RequestException as e:
            raise TGAppError(f"خطای اتصال: {str(e)[:100]}")

        # موفقیت: ریدایرکت به /apps یا پاسخ true
        if r.status_code == 200:
            try:
                data = r.json()
                if data is True or (isinstance(data, dict) and data.get("success")):
                    return True
                if isinstance(data, dict) and data.get("error"):
                    err = str(data["error"])
                    if "PHONE_CODE" in err.upper():
                        raise TGAppError("❌ کد اشتباه یا منقضی شده است.")
                    raise TGAppError(err)
            except ValueError:
                pass
            # ممکن است HTML باشد
            alert = _parse_alert(r.text)
            if alert:
                raise TGAppError(alert)
            # اگر صفحه apps برگشت یعنی وارد شدیم
            if "api" in r.url or "apps" in r.url:
                return True

        if r.status_code in (301, 302) or r.history:
            return True

        alert = _parse_alert(r.text)
        if alert:
            raise TGAppError(alert)
        if "stel_token" in self.session.cookies.get_dict():
            return True

        raise TGAppError("ورود ناموفق - احتمالاً کد اشتباه است")

    # ─── مرحله ۳: گرفتن/ساخت اپ ───

    @staticmethod
    def _extract_app_info(html):
        """استخراج اطلاعات اپ از صفحه /apps"""
        info = {}

        m = re.search(r'api_id\D{0,300}?(\d{4,12})', html, re.S)
        h = re.search(r'api_hash[\s\S]{0,300}?\b([0-9a-f]{32})\b', html, re.S)
        if m and h:
            info["api_id"] = int(m.group(1))
            info["api_hash"] = h.group(1)

        # اطلاعات تکمیلی اپ (اگر موجود باشد)
        for field in ("app_title", "app_shortname", "app_platform", "app_url"):
            m = re.search(
                rf'name="{field}"[^>]*value="([^"]*)"', html
            )
            if m:
                info[field] = m.group(1)

        return info if "api_id" in info else None

    def get_or_create_app(self, app_title, app_shortname):
        """
        اگر اپ موجود باشد → همان را برمی‌گرداند (existed=True)
        در غیر این صورت می‌سازد (existed=False)
        برمی‌گرداند: (info_dict, existed_bool)
        """
        try:
            r = self.session.get(f"{BASE}/apps", timeout=30)
        except requests.RequestException as e:
            raise TGAppError(f"خطای اتصال: {str(e)[:100]}")

        if "/auth" in r.url:
            raise TGAppError("نشست ورود منقضی شد؛ دوباره شروع کنید")

        # ۱) اپ از قبل موجود است؟
        existing = self._extract_app_info(r.text)
        if existing:
            return existing, True

        # ۲) ساخت اپ جدید
        try:
            r2 = self.session.post(
                f"{BASE}/apps/create",
                data={
                    "hash": self.random_hash,
                    "app_title": app_title,
                    "app_shortname": app_shortname,
                    "app_url": "",
                    "app_platform": "android",
                    "app_desc": "",
                },
                timeout=30,
            )
        except requests.RequestException as e:
            raise TGAppError(f"خطای اتصال: {str(e)[:100]}")

        alert = _parse_alert(r2.text)
        if alert:
            # اگر خطا مربوط به وجود اپ است، دوباره صفحه را بخوان
            info = self._extract_app_info(r2.text)
            if info:
                return info, True
            raise TGAppError(alert)

        info = self._extract_app_info(r2.text)
        if info:
            return info, False

        # شاید صفحه تغییر کرده - آخرین تلاش: get مجدد
        r3 = self.session.get(f"{BASE}/apps", timeout=30)
        info = self._extract_app_info(r3.text)
        if info:
            return info, False

        raise TGAppError(
            "نمی‌توان اطلاعات اپ را خواند. احتمالاً ساختار my.telegram.org "
            "تغییر کرده؛ از «ثبت دستی API» استفاده کنید."
        )
