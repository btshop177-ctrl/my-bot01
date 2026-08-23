"""
ماژول ردیابی پنل‌های باز
"""


class PanelTracker:
    def __init__(self, config_manager):
        self.config = config_manager

    def add_panel(self, chat_id, message_id):
        panels = self.config.get("open_panels", [])

        for p in panels:
            if p["chat_id"] == chat_id and p["message_id"] == message_id:
                return

        panels.append({
            "chat_id": chat_id,
            "message_id": message_id
        })
        self.config.set("open_panels", panels)

    def remove_panel(self, chat_id, message_id):
        panels = self.config.get("open_panels", [])
        new_panels = [
            p for p in panels
            if not (p["chat_id"] == chat_id and p["message_id"] == message_id)
        ]
        self.config.set("open_panels", new_panels)

    def get_panels_in_chat(self, chat_id):
        panels = self.config.get("open_panels", [])
        return [p for p in panels if p["chat_id"] == chat_id]

    def get_all_panels(self):
        return self.config.get("open_panels", [])

    def clear_chat_panels(self, chat_id):
        panels = self.config.get("open_panels", [])
        new_panels = [p for p in panels if p["chat_id"] != chat_id]
        self.config.set("open_panels", new_panels)

    def clear_all_panels(self):
        self.config.set("open_panels", [])

    async def close_panels_in_chat(self, client, chat_id):
        panels = self.get_panels_in_chat(chat_id)
        closed = 0
        failed = 0

        for p in panels:
            try:
                await client.delete_messages(
                    p["chat_id"],
                    p["message_id"]
                )
                closed += 1
            except Exception as e:
                failed += 1
                print(f"⚠️ خطا در حذف پنل: {e}")

        self.clear_chat_panels(chat_id)
        return closed, failed

    async def close_all_panels(self, client):
        panels = self.get_all_panels()
        closed = 0
        failed = 0

        for p in panels:
            try:
                await client.delete_messages(
                    p["chat_id"],
                    p["message_id"]
                )
                closed += 1
            except Exception as e:
                failed += 1

        self.clear_all_panels()
        return closed, failed