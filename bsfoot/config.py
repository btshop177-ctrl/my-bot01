import os
from dotenv import load_dotenv

load_dotenv()


def _env(name, default=None, required=False):
    val = os.getenv(name, default)
    if required and (val is None or str(val).strip() == ""):
        raise ValueError(f"'{name}' is required!")
    return val


def _int(name, default=0):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"'{name}' must be integer")


def _float(name, default=0.0):
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"'{name}' must be float")


BOT_TOKEN = _env("BOT_TOKEN", required=True)
PROXY_URL = _env("PROXY_URL", "")
PROXY_SOCKS5_URL = _env("PROXY_SOCKS5_URL", "")

ADMIN_IDS = [int(x.strip()) for x in _env("ADMIN_IDS", "").split(",") if x.strip()]
if not ADMIN_IDS:
    raise ValueError("At least one ADMIN_ID required!")

DATABASE_PATH = _env("DATABASE_PATH", "database.db")
COIN_NAME = _env("COIN_NAME", "سکه")
HOUSE_FEE = _float("HOUSE_FEE", 0.10)
MIN_BET = _int("MIN_BET", 100)
MAX_BET = _int("MAX_BET", 100000)
MIN_WITHDRAW = _int("MIN_WITHDRAW", 100)
BROADCAST_DELAY = _float("BROADCAST_DELAY", 0.1)

USERBOT_API_ID = _int("USERBOT_API_ID")
USERBOT_API_HASH = _env("USERBOT_API_HASH", "")
USERBOT_PHONE = _env("USERBOT_PHONE", "")
USERBOT_SESSION = _env("USERBOT_SESSION", "userbot_session")
BSLIFE_BOT = _env("BSLIFE_BOT", "BslifeBot")
BSLIFE_OUR_NAME = _env("BSLIFE_OUR_NAME", "negative")

USERBOT_PROXY_TYPE = _env("USERBOT_PROXY_TYPE", "")
USERBOT_PROXY_HOST = _env("USERBOT_PROXY_HOST", "")
USERBOT_PROXY_PORT = _int("USERBOT_PROXY_PORT", 0)