from pyrogram import Client
from datetime import datetime
import pytz
import asyncio
from dotenv import load_dotenv
import os
load_dotenv()

# ---------------------------------------------
# اطلاعات اکانت خود را وارد کنید
api_id = "30615378"  # جایگزین کنید
api_hash = "234c6bba94e99cf8d915c2fe26ca0e94"  # جایگزین کنید
phone_number = "+989372762206"
# ---------------------------------------------

app = Client("clock_satia", api_id=api_id, api_hash=api_hash, phone_number=phone_number)


def get_fancy_time():
    """
    تولید ساعت ایران با فونت و فرمت خاص
    """
    # تنظیم منطقه زمانی ایران
    tehran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran_tz)

    # فرمت ساعت:دقیقه
    time_str = now.strftime("%H:%M")

    # تبدیل اعداد به فونت توپر
    font_map = str.maketrans(
        "0123456789",
        "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    )

    fancy_digits = time_str.translate(font_map)

    # ساختار نهایی: ⌥ 𝟬𝟭:𝟮𝟯
    return f"⌥ {fancy_digits}"


async def main():
    async with app:
        print("✅ ربات Pyrogram روشن شد...")
        last_check = ""

        while True:
            try:
                # محاسبه زمان فعلی
                current_fancy_time = get_fancy_time()

                # اگر ساعت تغییر کرده بود، پروفایل را آپدیت کن
                if current_fancy_time != last_check:
                    # در پایروگرام برای تغییر نام خانوادگی از این متد استفاده می‌کنیم
                    await app.update_profile(last_name=current_fancy_time)
                    last_check = current_fancy_time
                    print(f"Last Name Updated: {current_fancy_time}")

                # همگام‌سازی با ثانیه 00
                # محاسبه می‌کنیم چقدر مانده تا دقیقه بعدی شروع شود
                now = datetime.now()
                seconds_to_sleep = 60 - now.second

                # یک ثانیه اضافه برای اطمینان از ورود به دقیقه جدید
                await asyncio.sleep(seconds_to_sleep)

            except Exception as e:
                print(f"Error: {e}")
                # در صورت خطا (مثلا قطعی اینترنت) ۱۰ ثانیه صبر کن
                await asyncio.sleep(10)


# اجرای برنامه
if __name__ == "__main__":
    app.run(main())