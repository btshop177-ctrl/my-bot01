"""
ماژول تپچی - ارسال خودکار بنر (تبلیغ) در گروه‌ها
"""

import asyncio


class BannerManager:
    def __init__(self, client, config_manager):
        self.client = client
        self.config = config_manager
        self.tasks = {}

    def is_enabled(self):
        return self.config.get("tapchi_enabled", False)

    def enable(self):
        self.config.set("tapchi_enabled", True)
        self.start_all()
        return "✅ **تپچی روشن شد**\nهمه بنرهای فعال شروع به ارسال کردند."

    def disable(self):
        self.config.set("tapchi_enabled", False)
        self.stop_all()
        return "🔴 **تپچی خاموش شد**\nتمام بنرهای فعال متوقف شدند."

    def get_mode(self):
        return self.config.get("banner_mode", "forward")

    def set_mode(self, mode):
        if mode not in ("forward", "copy"):
            return "❌ حالت نامعتبر"
        self.config.set("banner_mode", mode)
        mode_fa = "فوروارد" if mode == "forward" else "کپی"
        return f"✅ **حالت بنر تنظیم شد:** {mode_fa}"

    def add_banner(self, chat_id, chat_name, from_chat_id, message_id, interval):
        banners = self.config.get("banners", {})
        chat_key = str(chat_id)

        if chat_key not in banners:
            banners[chat_key] = {
                "chat_name": chat_name,
                "list": []
            }

        chat_banners = banners[chat_key]["list"]
        new_id = max([b["id"] for b in chat_banners], default=0) + 1

        banner = {
            "id": new_id,
            "from_chat_id": from_chat_id,
            "message_id": message_id,
            "interval": interval,
            "enabled": True
        }
        chat_banners.append(banner)
        banners[chat_key]["chat_name"] = chat_name
        self.config.set("banners", banners)

        if self.is_enabled():
            self._start_banner_task(chat_id, banner)

        return (f"✅ **بنر جدید ثبت شد**\n\n"
                f"  ▸ شماره: `{new_id}`\n"
                f"  ▸ چت: **{chat_name}**\n"
                f"  ▸ فاصله: `{interval}` ثانیه\n"
                f"  ▸ حالت: `{self.get_mode()}`")

    def remove_banner(self, chat_id, banner_id):
        banners = self.config.get("banners", {})
        chat_key = str(chat_id)

        if chat_key not in banners:
            return "❌ در این چت بنری ثبت نشده"

        chat_banners = banners[chat_key]["list"]
        new_list = [b for b in chat_banners if b["id"] != banner_id]

        if len(new_list) == len(chat_banners):
            return f"❌ بنر با شماره `{banner_id}` یافت نشد"

        banners[chat_key]["list"] = new_list

        if not new_list:
            del banners[chat_key]

        self.config.set("banners", banners)
        self._stop_banner_task(chat_id, banner_id)
        return f"✅ بنر `{banner_id}` حذف شد"

    def clear_chat_banners(self, chat_id):
        banners = self.config.get("banners", {})
        chat_key = str(chat_id)

        if chat_key not in banners:
            return "❌ در این چت بنری نیست"

        for banner in banners[chat_key]["list"]:
            self._stop_banner_task(chat_id, banner["id"])

        del banners[chat_key]
        self.config.set("banners", banners)
        return "🗑 تمام بنرهای این چت حذف شد"

    def clear_all_banners(self):
        self.stop_all()
        self.config.set("banners", {})
        return "🗑 **تمام بنرها در همه چت‌ها حذف شدند**"

    def get_chat_list(self, chat_id):
        banners = self.config.get("banners", {})
        chat_key = str(chat_id)

        if chat_key not in banners or not banners[chat_key]["list"]:
            return "📭 در این چت بنری ثبت نشده"

        chat_data = banners[chat_key]
        text = f"📋 **بنرهای فعال در {chat_data['chat_name']}:**\n\n"

        mode = self.get_mode()
        mode_fa = "فوروارد" if mode == "forward" else "کپی"

        for b in chat_data["list"]:
            status = "🟢" if b.get("enabled", True) else "🔴"
            text += f"  {status} **شماره:** `{b['id']}`\n"
            text += f"       فاصله: `{b['interval']}` ثانیه\n"
            text += f"       حالت: `{mode_fa}`\n\n"

        global_status = "🟢 روشن" if self.is_enabled() else "🔴 خاموش"
        text += f"**وضعیت کلی تپچی:** {global_status}"
        return text

    def get_full_list(self):
        banners = self.config.get("banners", {})

        if not banners:
            return "📭 هیچ بنری در هیچ چتی ثبت نشده"

        text = "📋 **لیست کامل بنرها:**\n\n"
        for chat_key, data in banners.items():
            text += f"💬 **{data['chat_name']}** (`{chat_key}`)\n"
            for b in data["list"]:
                status = "🟢" if b.get("enabled", True) else "🔴"
                text += f"  {status} `{b['id']}` ▸ هر `{b['interval']}` ثانیه\n"
            text += "\n"

        global_status = "🟢 روشن" if self.is_enabled() else "🔴 خاموش"
        text += f"**وضعیت کلی:** {global_status}\n"
        text += f"**حالت پیش‌فرض:** `{self.get_mode()}`"
        return text

    def start_all(self):
        self.stop_all()
        banners = self.config.get("banners", {})
        count = 0
        for chat_key, data in banners.items():
            chat_id = int(chat_key)
            for banner in data["list"]:
                if banner.get("enabled", True):
                    self._start_banner_task(chat_id, banner)
                    count += 1
        print(f"🚀 {count} بنر شروع به کار کرد")

    def stop_all(self):
        for key, task in list(self.tasks.items()):
            if not task.done():
                task.cancel()
        self.tasks.clear()

    def _start_banner_task(self, chat_id, banner):
        key = (chat_id, banner["id"])
        if key in self.tasks and not self.tasks[key].done():
            return
        task = asyncio.ensure_future(self._banner_loop(chat_id, banner))
        self.tasks[key] = task

    def _stop_banner_task(self, chat_id, banner_id):
        key = (chat_id, banner_id)
        if key in self.tasks:
            task = self.tasks[key]
            if not task.done():
                task.cancel()
            del self.tasks[key]

    async def _banner_loop(self, chat_id, banner):
        banner_id = banner["id"]
        from_chat_id = banner["from_chat_id"]
        message_id = banner["message_id"]
        interval = banner["interval"]

        await asyncio.sleep(interval)

        while self.is_enabled():
            banners = self.config.get("banners", {})
            chat_key = str(chat_id)
            if chat_key not in banners:
                break
            still_exists = any(b["id"] == banner_id for b in banners[chat_key]["list"])
            if not still_exists:
                break

            try:
                mode = self.get_mode()

                if mode == "forward":
                    await self.client.forward_messages(
                        entity=chat_id,
                        messages=message_id,
                        from_peer=from_chat_id
                    )
                else:
                    msg = await self.client.get_messages(from_chat_id, ids=message_id)
                    if msg:
                        if msg.media:
                            await self.client.send_file(
                                chat_id,
                                msg.media,
                                caption=msg.text or ""
                            )
                        else:
                            await self.client.send_message(chat_id, msg.text or "")

                print(f"📤 بنر {banner_id} ارسال شد به {chat_id}")

            except Exception as e:
                error = str(e)
                if "FLOOD" in error.upper():
                    print(f"⏳ بنر {banner_id}: Flood wait")
                    await asyncio.sleep(30)
                else:
                    print(f"❌ خطا در بنر {banner_id}: {error[:80]}")

            await asyncio.sleep(interval)

        print(f"🛑 حلقه بنر {banner_id} در {chat_id} پایان یافت")