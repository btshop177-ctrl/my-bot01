import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DB_PATH = "bot_database.db"

# تنظیمات پراکسی
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
PROXY_URL = os.getenv("PROXY_URL", "socks5://127.0.0.1:10808")

# مدت سکوت (ثانیه) - 1 روز
MUTE_DURATION = 86400