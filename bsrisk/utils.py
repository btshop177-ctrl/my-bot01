import html
import re


# الگوی کاراکترهای کنترلی نامرئی
INVISIBLE_CHARS_PATTERN = re.compile(
    r'[\u0000-\u001F\u007F-\u009F\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]'
)


def clean_text(text: str) -> str:
    """حذف کاراکترهای کنترلی نامرئی"""
    if not text:
        return ""
    cleaned = INVISIBLE_CHARS_PATTERN.sub('', text)
    return cleaned.strip()


def escape_html(text: str) -> str:
    """escape امن HTML"""
    if not text:
        return ""
    return html.escape(clean_text(text), quote=False)


def user_mention(user_id: int, display_name: str = None, user_obj=None) -> str:
    """ساخت لینک mention با HTML"""
    name = ""

    if user_obj is not None:
        if user_obj['full_name']:
            cleaned = clean_text(user_obj['full_name'])
            if cleaned:
                name = cleaned
        if not name and user_obj['username']:
            name = f"@{user_obj['username']}"
    else:
        if display_name:
            name = clean_text(display_name)

    if not name:
        name = f"User{user_id}"

    safe_name = html.escape(name, quote=False)
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


def get_display_name(user) -> str:
    """دریافت نام نمایشی کاربر"""
    if user['full_name']:
        cleaned = clean_text(user['full_name'])
        if cleaned:
            return cleaned
    if user['username']:
        return f"@{user['username']}"
    return f"User{user['user_id']}"