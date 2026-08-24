# profit.py - نسخه توربو و فوق‌سریع

_EXCLUDED_1 = frozenset({"cm", "orb", "spike", "hat", "sol", "spidy"})
_EXCLUDED_2 = frozenset({"cm", "orb", "spike", "hat", "sol", "spidy", "plasma"})


def profit_check(price_sells: int, price_profit: int, cod: str, unit_price: int) -> bool:
    # ─── ۱. شرط‌های کلی (بر اساس سود و قیمت کل بدون وابستگی به unit_price) ───
    if price_sells <= 1000 and price_profit >= 850:
        return True
    if price_sells <= 3000 and price_profit >= 6000:
        return True
    if price_sells <= 5000 and price_profit >= 8000 and cod not in _EXCLUDED_1:
        return True
    if price_sells <= 15000 and price_profit >= 9500 and cod not in _EXCLUDED_2:
        return True
    if price_sells <= 30000 and price_profit >= 23000 and cod not in _EXCLUDED_2:
        return True

    # ─── ۲. شرط‌های دسته‌بندی‌شده بر اساس unit_price (شاخه فوق‌سریع) ───
    if unit_price == 4:
        if price_sells <= 51 and price_profit >= 149: return True
        if price_sells <= 101 and price_profit >= 299: return True
        if price_sells <= 201 and price_profit >= 495: return True
        if price_sells <= 310 and price_profit >= 650: return True

    elif unit_price == 200:
        if price_sells <= 55 and price_profit >= 149: return True
        if price_sells <= 300 and price_profit >= 500: return True

    elif unit_price == 150:
        if price_sells <= 100 and price_profit >= 99: return True
        if price_sells <= 300 and price_profit >= 550: return True

    elif unit_price == 300:
        if 50 <= price_sells <= 100 and price_profit >= 200: return True
        if 100 <= price_sells <= 500 and price_profit >= 750: return True

    elif unit_price == 70:
        if price_sells <= 60 and price_profit >= 160: return True
        if price_sells <= 300 and price_profit >= 600: return True

    elif unit_price == 2:
        if price_sells <= 300 and price_profit >= 450: return True
        if price_sells <= 600 and price_profit >= 850: return True

    elif unit_price == 10:
        if price_sells <= 100 and price_profit >= 350: return True
        if price_sells <= 200 and price_profit >= 550: return True
        if price_sells <= 300 and price_profit >= 650: return True

    elif unit_price == 30:
        if price_sells <= 100 and price_profit >= 450: return True
        if price_sells <= 300 and price_profit >= 700: return True

    elif unit_price == 40:
        if price_sells <= 50 and price_profit >= 250: return True
        if price_sells <= 100 and price_profit >= 500: return True

    elif unit_price == 1:
        if price_sells <= 300 and price_profit >= 450: return True

    elif unit_price == 3:
        if price_sells <= 300 and price_profit >= 600: return True

    elif unit_price in (6, 7):
        if price_sells <= 300 and price_profit >= 650: return True

    elif unit_price == 9:
        if price_sells <= 300 and price_profit >= 750: return True

    elif unit_price > 300:
        if price_sells <= 200 and price_profit >= 400: return True

    return False