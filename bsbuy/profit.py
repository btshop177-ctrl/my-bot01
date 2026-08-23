_EXCLUDED_1 = frozenset({"cm", "orb", "spike", "hat", "sol", "spidy"})
_EXCLUDED_2 = frozenset({"cm", "orb", "spike", "hat", "sol", "spidy", "plasma"})


def profit_check(price_sells, price_profit, cod, unit_price):
    if 51 >= price_sells and price_profit >= 149 and unit_price == 4:
        return True
    if 55 >= price_sells and price_profit >= 149 and unit_price == 200:
        return True
    if 300 >= price_sells and price_profit >= 500 and unit_price == 200:
        return True
    if 100 >= price_sells and price_profit >= 99 and unit_price == 150:
        return True
    if 300 >= price_sells and price_profit >= 550 and unit_price == 150:
        return True
    if 100 >= price_sells >= 50 and price_profit >= 200 and unit_price == 300:
        return True
    if 500 >= price_sells >= 100 and price_profit >= 750 and unit_price == 300:
        return True
    if 60 >= price_sells and price_profit >= 160 and unit_price == 70:
        return True
    if 300 >= price_sells and price_profit >= 600 and unit_price == 70:
        return True
    if 300 >= price_sells and price_profit >= 450 and unit_price == 2:
        return True
    if 300 >= price_sells and price_profit >= 600 and unit_price == 3:
        return True
    if 101 >= price_sells and price_profit >= 299 and unit_price == 4:
        return True
    if 200 >= price_sells and price_profit >= 400 and unit_price > 300:
        return True
    if 300 >= price_sells and price_profit >= 450 and unit_price == 1:
        return True
    if 300 >= price_sells and price_profit >= 650 and unit_price == 6:
        return True
    if 300 >= price_sells and price_profit >= 650 and unit_price == 7:
        return True
    if 300 >= price_sells and price_profit >= 750 and unit_price == 9:
        return True
    if 300 >= price_sells and price_profit >= 650 and unit_price == 10:
        return True
    if 100 >= price_sells and price_profit >= 350 and unit_price == 10:
        return True
    if 200 >= price_sells and price_profit >= 550 and unit_price == 10:
        return True
    if 100 >= price_sells and price_profit >= 450 and unit_price == 30:
        return True
    if 300 >= price_sells and price_profit >= 700 and unit_price == 30:
        return True
    if 201 >= price_sells and price_profit >= 495 and unit_price == 4:
        return True
    if 310 >= price_sells and price_profit >= 650 and unit_price == 4:
        return True
    if 600 >= price_sells and price_profit >= 850 and unit_price == 2:
        return True
    if 50 >= price_sells and price_profit >= 250 and unit_price == 40:
        return True
    if 100 >= price_sells and price_profit >= 500 and unit_price == 40:
        return True
    if 1000 >= price_sells and price_profit >= 850:
        return True
    if 3000 >= price_sells and price_profit >= 6000:
        return True
    if 5000 >= price_sells and price_profit >= 8000 and cod not in _EXCLUDED_1:
        return True
    if 15000 >= price_sells and price_profit >= 9500 and cod not in _EXCLUDED_2:
        return True
    if 30000 >= price_sells and price_profit >= 23000 and cod not in _EXCLUDED_2:
        return True

    return False


def main():
    pass


if __name__ == '__main__':
    main()