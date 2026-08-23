"""
مدیریت فونت‌های ساعت
"""

FONT_MAP = {
    1: {
        "name": "🄁🄂:🄃🄄",
        "chars": "🄀🄁🄂🄃🄄🄅🄆🄇🄈🄉"
    },
    2: {
        "name": "𝟏𝟐:𝟑𝟒",
        "chars": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
    },
    3: {
        "name": "ϩ𝟷:4Ϭ",
        "chars": "Ϭ𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"
    },
    4: {
        "name": "¹²:³⁴",
        "chars": "⁰¹²³⁴⁵⁶⁷⁸⁹"
    },
    5: {
        "name": "₁₂:₃₄",
        "chars": "₀₁₂₃₄₅₆₇₈₉"
    },
    6: {
        "name": "❶❷:❸❹",
        "chars": "⓪❶❷❸❹❺❻❼❽❾"
    },
    7: {
        "name": "¹² ³⁴",
        "chars": "⁰¹²³⁴⁵⁶⁷⁸⁹"
    },
    8: {
        "name": "𝟷𝟸:𝟹𝟺",
        "chars": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"
    },
    9: {
        "name": "𝟭𝟮:𝟯𝟰",
        "chars": "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    },
    10: {
        "name": "𝟙𝟚:𝟛𝟜",
        "chars": "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"
    },
    11: {
        "name": "①②:③④",
        "chars": "⓪①②③④⑤⑥⑦⑧⑨"
    },
    12: {
        "name": "❶②:❸④",
        "chars": "⓪❶②❸④⑤❻⑦❽⑨"
    },
}


def convert_time(time_str: str, font_id: int) -> str:
    """تبدیل رشته ساعت به فونت انتخابی"""
    if font_id not in FONT_MAP:
        font_id = 9

    chars = FONT_MAP[font_id]["chars"]
    result = ""
    for ch in time_str:
        if ch.isdigit():
            result += chars[int(ch)]
        else:
            result += ch
    return result


def get_font_list() -> str:
    """لیست تمام فونت‌ها"""
    text = "🔤 **لیست فونت‌های ساعت:**\n\n"
    for fid, fdata in FONT_MAP.items():
        text += f"  `{fid}` ▸ {fdata['name']}\n"
    return text