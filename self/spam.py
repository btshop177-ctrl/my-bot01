"""
ماژول اسپم - چند اسپم همزمان با افکت، تارگت، ریپلای و متن خاص
نسخه اصلاح‌شده:
  - اسپم متنی: صبر → ریپلای
  - اسپم تارگتی: منتظر پیام جدید طرف → صبر → ریپلای
  - اسپم عادی: بدون تغییر
  - رفع باگ‌های جزئی
"""

import asyncio
import time
import re


class SpamManager:
    def __init__(self, client, effect_manager=None, config_manager=None):
        self.client = client
        self.effects = effect_manager
        self.config = config_manager
        self.active_spams = {}
        self.text_spams = {}
        self.target_spams = {}
        self._target_handlers = {}

    def _next_id(self, chat_id):
        if chat_id not in self.active_spams:
            return 1
        existing_ids = list(self.active_spams[chat_id].keys())
        return max(existing_ids, default=0) + 1

    def _next_text_spam_id(self):
        if not self.text_spams:
            return 1
        return max(self.text_spams.keys(), default=0) + 1

    def _next_target_spam_id(self):
        all_ids = []
        for chat_data in self.target_spams.values():
            for data in chat_data.values():
                all_ids.append(data.get("id", 0))
        return max(all_ids, default=0) + 1

    def is_spam_active(self, chat_id, spam_id=None):
        if chat_id not in self.active_spams:
            return False
        if spam_id is None:
            for sid, data in self.active_spams[chat_id].items():
                if not data["task"].done():
                    return True
            return False
        else:
            if spam_id not in self.active_spams[chat_id]:
                return False
            return not self.active_spams[chat_id][spam_id]["task"].done()

    async def stop_spam(self, chat_id, spam_id=None):
        stopped = 0

        if chat_id in self.active_spams:
            if spam_id is not None:
                if spam_id in self.active_spams[chat_id]:
                    data = self.active_spams[chat_id][spam_id]
                    if not data["task"].done():
                        data["task"].cancel()
                        stopped = 1
                    del self.active_spams[chat_id][spam_id]
                    if not self.active_spams[chat_id]:
                        del self.active_spams[chat_id]
            else:
                for sid, data in list(self.active_spams[chat_id].items()):
                    if not data["task"].done():
                        data["task"].cancel()
                        stopped += 1
                del self.active_spams[chat_id]

        if spam_id is None and chat_id in self.target_spams:
            for target_id, data in list(
                self.target_spams[chat_id].items()
            ):
                data["active"] = False
                stopped += 1
            del self.target_spams[chat_id]

        return stopped

    def stop_all(self):
        total = 0

        for chat_id in list(self.active_spams.keys()):
            for sid, data in list(self.active_spams[chat_id].items()):
                if not data["task"].done():
                    data["task"].cancel()
                    total += 1
        self.active_spams.clear()

        for ts_id, data in list(self.text_spams.items()):
            total += 1
        self.text_spams.clear()

        for chat_id, targets in list(self.target_spams.items()):
            for target_id, data in targets.items():
                data["active"] = False
                total += 1
        self.target_spams.clear()

        return total

    # ═══════════════════════════════════════
    # افکت
    # ═══════════════════════════════════════

    def _apply_effects_to_text(self, text):
        if not self.effects or not self.config:
            return text, False

        active_effects = self.config.get("active_effects", [])
        if not active_effects:
            return text, False

        if "gradual" in active_effects:
            active_effects = [
                e for e in active_effects if e != "gradual"
            ]
            if not active_effects:
                return text, False

        try:
            processed, use_html = self.effects._process_text_full(
                text, active_effects
            )
            return processed, use_html
        except Exception as e:
            print(f"⚠️ خطا در افکت اسپم: {e}")
            return text, False

    def _extract_flood_wait(self, error_str):
        match = re.search(
            r'(\d+)\s*(?:seconds?|s)', error_str, re.IGNORECASE
        )
        if match:
            return int(match.group(1))
        return 5

    # ═══════════════════════════════════════
    # ارسال پیام مشترک
    # ═══════════════════════════════════════

    async def _send_message(self, chat_id, text, reply_to=None):
        """ارسال پیام با افکت"""
        processed_text, use_html = self._apply_effects_to_text(text)

        send_kwargs = {
            "entity": chat_id,
            "message": processed_text,
        }

        if use_html:
            send_kwargs["parse_mode"] = 'html'

        if reply_to:
            send_kwargs["reply_to"] = reply_to

        try:
            msg = await self.client.send_message(**send_kwargs)
            return msg
        except Exception as e:
            error = str(e).upper()
            if "ENTITY" in error or "PARSE" in error:
                kwargs = {"entity": chat_id, "message": text}
                if reply_to:
                    kwargs["reply_to"] = reply_to
                return await self.client.send_message(**kwargs)
            raise

    # ═══════════════════════════════════════
    # اسپم متنی (trigger-based)
    # ═══════════════════════════════════════

    def add_text_spam(self, keyword, text, delay, count=None):
        ts_id = self._next_text_spam_id()
        self.text_spams[ts_id] = {
            "keyword": keyword,
            "text": text,
            "delay": delay,
            "count": count,
            "sent": 0,
            "active": True
        }
        return ts_id

    def remove_text_spam(self, ts_id):
        if ts_id in self.text_spams:
            del self.text_spams[ts_id]
            return True
        return False

    async def handle_text_trigger(self, event):
        """بررسی پیام‌های ورودی برای اسپم متنی"""
        msg_text = event.raw_text or ""
        if not msg_text:
            return

        msg_words = msg_text.split()

        for ts_id, data in list(self.text_spams.items()):
            if not data.get("active", True):
                continue

            keyword = data["keyword"]
            if (keyword == msg_text
                    or keyword in msg_words
                    or keyword.lower() in msg_text.lower()):
                asyncio.ensure_future(
                    self._text_spam_send(
                        event.chat_id, ts_id, data, event.id
                    )
                )

    async def _text_spam_send(self, chat_id, ts_id, data, reply_to_id):
        """اسپم متنی: صبر → ریپلای"""
        try:
            await asyncio.sleep(data["delay"])

            if ts_id not in self.text_spams:
                return
            if not self.text_spams[ts_id].get("active", True):
                return

            await self._send_message(
                chat_id, data["text"], reply_to=reply_to_id
            )

            if ts_id in self.text_spams:
                self.text_spams[ts_id]["sent"] += 1

                if (data["count"]
                        and self.text_spams[ts_id]["sent"] >= data["count"]):
                    self.text_spams[ts_id]["active"] = False
                    print(f"✅ اسپم متنی [{ts_id}] پایان یافت")

            print(
                f"📤 اسپم متنی [{ts_id}] ارسال شد "
                f"(بعد از {data['delay']}s)"
            )

        except Exception as e:
            print(
                f"⚠️ خطا در اسپم متنی [{ts_id}]: {str(e)[:80]}"
            )

    # ═══════════════════════════════════════
    # اسپم تارگتی
    # ═══════════════════════════════════════

    def add_target_spam(self, chat_id, target_id, text, delay,
                        count=None, chat_name="", target_name=""):
        ts_id = self._next_target_spam_id()

        if chat_id not in self.target_spams:
            self.target_spams[chat_id] = {}

        self.target_spams[chat_id][target_id] = {
            "id": ts_id,
            "text": text,
            "delay": delay,
            "count": count,
            "sent": 0,
            "active": True,
            "chat_name": chat_name,
            "target_name": target_name,
            "started_at": time.time(),
        }

        print(
            f"🎯 اسپم تارگتی [{ts_id}] ثبت شد | "
            f"چت: {chat_id} | تارگت: {target_id} | تاخیر: {delay}s"
        )
        return ts_id

    async def handle_target_trigger(self, event):
        """بررسی پیام‌های ورودی برای اسپم تارگتی"""
        sender_id = event.sender_id
        chat_id = event.chat_id

        if not sender_id:
            return

        if chat_id not in self.target_spams:
            return

        if sender_id not in self.target_spams[chat_id]:
            return

        data = self.target_spams[chat_id][sender_id]

        if not data.get("active", True):
            return

        if data["count"] and data["sent"] >= data["count"]:
            data["active"] = False
            print(f"✅ اسپم تارگتی [{data['id']}] پایان (تعداد)")
            return

        asyncio.ensure_future(
            self._target_spam_send(
                chat_id, sender_id, data, event.id
            )
        )

    async def _target_spam_send(self, chat_id, target_id,
                                data, reply_to_id):
        """اسپم تارگتی: صبر → ریپلای"""
        try:
            await asyncio.sleep(data["delay"])

            if chat_id not in self.target_spams:
                return
            if target_id not in self.target_spams[chat_id]:
                return
            if not self.target_spams[chat_id][target_id].get(
                "active", True
            ):
                return

            await self._send_message(
                chat_id, data["text"], reply_to=reply_to_id
            )

            if (chat_id in self.target_spams
                    and target_id in self.target_spams[chat_id]):
                self.target_spams[chat_id][target_id]["sent"] += 1
                sent = self.target_spams[chat_id][target_id]["sent"]

                if data["count"] and sent >= data["count"]:
                    self.target_spams[chat_id][target_id]["active"] = False
                    print(
                        f"✅ اسپم تارگتی [{data['id']}] پایان یافت"
                    )

            print(
                f"📤 اسپم تارگتی [{data['id']}] ارسال شد → "
                f"ریپلای روی {target_id} (بعد از {data['delay']}s)"
            )

        except Exception as e:
            error = str(e).upper()
            if "FLOOD" in error or "WAIT" in error:
                wait = self._extract_flood_wait(str(e))
                print(
                    f"⏳ تارگت اسپم [{data['id']}]: Flood {wait}s"
                )
            else:
                print(
                    f"⚠️ خطا در اسپم تارگتی [{data['id']}]: "
                    f"{str(e)[:80]}"
                )

    def stop_target_spam(self, chat_id, target_id=None):
        """توقف اسپم تارگتی"""
        if chat_id not in self.target_spams:
            return 0

        stopped = 0
        if target_id:
            if target_id in self.target_spams[chat_id]:
                self.target_spams[chat_id][target_id]["active"] = False
                del self.target_spams[chat_id][target_id]
                stopped = 1
                if not self.target_spams[chat_id]:
                    del self.target_spams[chat_id]
        else:
            for tid, data in self.target_spams[chat_id].items():
                data["active"] = False
                stopped += 1
            del self.target_spams[chat_id]

        return stopped

    # ═══════════════════════════════════════
    # اسپم عادی
    # ═══════════════════════════════════════

    async def start_spam(self, chat_id, text, delay, count=None,
                         delete=False, reply_to=None):
        spam_id = self._next_id(chat_id)

        task = asyncio.ensure_future(
            self._spam_loop(
                chat_id, spam_id, text, delay, count,
                delete, reply_to
            )
        )

        if chat_id not in self.active_spams:
            self.active_spams[chat_id] = {}

        self.active_spams[chat_id][spam_id] = {
            "task": task,
            "text": text,
            "delay": delay,
            "count": count,
            "delete": delete,
            "reply_to": reply_to,
            "started_at": time.time(),
            "sent": 0
        }

        return spam_id

    async def _spam_loop(self, chat_id, spam_id, text, delay, count,
                         delete, reply_to):
        sent_count = 0
        last_msg = None

        try:
            print(
                f"🚀 اسپم [{spam_id}] شروع در {chat_id} - "
                f"تاخیر: {delay}s"
                + (f" - ریپلای: {reply_to}" if reply_to else "")
            )

            while True:
                if count is not None and sent_count >= count:
                    print(
                        f"✅ اسپم [{spam_id}] پایان "
                        f"(تعداد: {sent_count})"
                    )
                    break

                try:
                    new_msg = await self._send_message(
                        chat_id, text, reply_to=reply_to
                    )

                    sent_count += 1

                    if (chat_id in self.active_spams
                            and spam_id in self.active_spams[chat_id]):
                        self.active_spams[chat_id][spam_id][
                            "sent"
                        ] = sent_count

                    print(
                        f"📤 اسپم [{spam_id}] #{sent_count} "
                        f"در {chat_id}"
                    )

                    if delete and last_msg is not None:
                        try:
                            await last_msg.delete()
                        except:
                            pass

                    last_msg = new_msg

                except asyncio.CancelledError:
                    raise

                except Exception as e:
                    error = str(e)
                    error_upper = error.upper()

                    if ("FLOOD" in error_upper
                            or "WAIT" in error_upper):
                        wait_time = self._extract_flood_wait(error)
                        print(
                            f"⏳ [{spam_id}] Flood wait: {wait_time}s"
                        )
                        await asyncio.sleep(wait_time + 1)
                        continue

                    elif ("SLOWMODE" in error_upper
                          or "SLOW_MODE" in error_upper):
                        wait_time = (
                            self._extract_flood_wait(error) or 10
                        )
                        print(
                            f"🔇 [{spam_id}] SlowMode: {wait_time}s"
                        )
                        await asyncio.sleep(wait_time + 1)
                        continue

                    elif ("CHAT_WRITE_FORBIDDEN" in error_upper
                          or "USER_BANNED" in error_upper):
                        print(
                            f"❌ [{spam_id}] اجازه ارسال ندارید"
                        )
                        break

                    elif ("MUTE" in error_upper
                          or "SILENT" in error_upper):
                        print(f"🤐 [{spam_id}] سکوت هستید")
                        await asyncio.sleep(30)
                        continue

                    else:
                        print(
                            f"⚠️ [{spam_id}] خطا: {error[:80]}"
                        )
                        await asyncio.sleep(5)
                        continue

                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            print(
                f"🛑 اسپم [{spam_id}] متوقف - ارسال: {sent_count}"
            )
            if delete and last_msg:
                try:
                    await last_msg.delete()
                except:
                    pass
            raise

        except Exception as e:
            print(f"❌ [{spam_id}] خطای کلی: {str(e)[:80]}")

        finally:
            if (chat_id in self.active_spams
                    and spam_id in self.active_spams[chat_id]):
                del self.active_spams[chat_id][spam_id]
                if not self.active_spams[chat_id]:
                    del self.active_spams[chat_id]

    # ═══════════════════════════════════════
    # وضعیت و لیست
    # ═══════════════════════════════════════

    def get_chat_spams(self, chat_id):
        if chat_id not in self.active_spams:
            return []
        result = []
        for sid, data in self.active_spams[chat_id].items():
            if not data["task"].done():
                result.append({
                    "id": sid,
                    "text": data["text"],
                    "delay": data["delay"],
                    "count": data["count"],
                    "delete": data["delete"],
                    "sent": data["sent"],
                    "started_at": data["started_at"],
                    "reply_to": data.get("reply_to"),
                    "type": "عادی",
                })
        return result

    def get_all_chats_with_spam(self):
        result = {}
        for chat_id, spams in self.active_spams.items():
            active = [
                (sid, data)
                for sid, data in spams.items()
                if not data["task"].done()
            ]
            if active:
                result[chat_id] = active
        return result

    def get_text_spams_list(self):
        return {
            k: v for k, v in self.text_spams.items()
            if v.get("active")
        }

    def get_target_spams_list(self):
        result = {}
        for chat_id, targets in self.target_spams.items():
            active = {
                tid: data
                for tid, data in targets.items()
                if data.get("active")
            }
            if active:
                result[chat_id] = active
        return result

    def get_chat_status_text(self, chat_id):
        spams = self.get_chat_spams(chat_id)
        target_spams = self.target_spams.get(chat_id, {})
        active_targets = {
            tid: d
            for tid, d in target_spams.items()
            if d.get("active")
        }

        if not spams and not active_targets:
            return "📭 **در این چت اسپمی فعال نیست**"

        text = ""
        total = len(spams) + len(active_targets)
        text += f"📋 **اسپم‌های فعال در این چت:** `{total}`\n\n"

        if spams:
            text += "**📤 اسپم عادی:**\n"
            for s in spams:
                elapsed = int(time.time() - s["started_at"])
                mode = "🗑 حذفی" if s["delete"] else "📤 معمولی"
                count_info = (
                    f"{s['sent']}/{s['count']}"
                    if s['count'] else f"{s['sent']}/∞"
                )
                text_preview = s["text"][:30] + (
                    "..." if len(s["text"]) > 30 else ""
                )

                text += f"  🔹 شماره: `{s['id']}`\n"
                text += f"      ▸ متن: `{text_preview}`\n"
                text += f"      ▸ تاخیر: `{s['delay']}s`\n"
                text += f"      ▸ ارسال: `{count_info}`\n"
                text += f"      ▸ حالت: {mode}\n"
                text += f"      ▸ زمان: `{elapsed}s` گذشته\n"
                if s.get("reply_to"):
                    text += f"      ▸ ریپلای: `{s['reply_to']}`\n"
                text += "\n"

        if active_targets:
            text += "**🎯 اسپم تارگتی:**\n"
            for tid, d in active_targets.items():
                elapsed = int(
                    time.time() - d.get("started_at", time.time())
                )
                count_info = (
                    f"{d['sent']}/{d['count']}"
                    if d['count'] else f"{d['sent']}/∞"
                )
                target_name = d.get("target_name", str(tid))
                text_preview = d["text"][:30] + (
                    "..." if len(d["text"]) > 30 else ""
                )

                text += f"  🎯 شماره: `{d['id']}`\n"
                text += (
                    f"      ▸ تارگت: {target_name} "
                    f"(`{tid}`)\n"
                )
                text += f"      ▸ متن: `{text_preview}`\n"
                text += f"      ▸ تاخیر: `{d['delay']}s`\n"
                text += f"      ▸ ارسال: `{count_info}`\n"
                text += (
                    f"      ▸ زمان: `{elapsed}s` گذشته\n\n"
                )

        text += (
            "**دستورات:**\n"
            "`اسپم توقف [شماره]` - توقف یک اسپم\n"
            "`اسپم توقف` - توقف همه اسپم‌های این چت\n"
            "`اسپم توقف همه` - توقف کل اسپم‌ها"
        )
        return text

    def get_full_status_text(self):
        all_chats = self.get_all_chats_with_spam()
        text_spams = self.get_text_spams_list()
        target_spams = self.get_target_spams_list()

        if not all_chats and not text_spams and not target_spams:
            return "📭 **هیچ اسپم فعالی وجود ندارد**"

        total_spams = sum(len(spams) for spams in all_chats.values())
        total_targets = sum(
            len(t) for t in target_spams.values()
        )

        text = f"📊 **آمار کلی اسپم‌ها**\n\n"
        text += f"  ▸ چت‌ها: `{len(all_chats)}`\n"
        text += f"  ▸ اسپم عادی: `{total_spams}`\n"

        if text_spams:
            text += f"  ▸ اسپم متنی: `{len(text_spams)}`\n"

        if target_spams:
            text += f"  ▸ اسپم تارگتی: `{total_targets}`\n"

        text += "\n"

        for chat_id, spams in all_chats.items():
            text += (
                f"💬 **چت `{chat_id}`:** "
                f"`{len(spams)}` اسپم\n"
            )
            for sid, data in spams:
                mode = "🗑" if data["delete"] else "📤"
                text_preview = data["text"][:20]
                text += (
                    f"  {mode} `{sid}` → `{text_preview}` "
                    f"(هر {data['delay']}s)\n"
                )
            text += "\n"

        if target_spams:
            text += "🎯 **اسپم‌های تارگتی:**\n"
            for chat_id, targets in target_spams.items():
                for tid, data in targets.items():
                    target_name = data.get("target_name", str(tid))
                    count = (
                        f"{data['sent']}/{data['count']}"
                        if data['count'] else f"{data['sent']}/∞"
                    )
                    text += (
                        f"  🎯 `{data['id']}` ▸ {target_name} "
                        f"→ `{data['text'][:20]}` ({count})\n"
                    )
            text += "\n"

        if text_spams:
            text += "📝 **اسپم‌های متنی:**\n"
            for ts_id, data in text_spams.items():
                count = (
                    f"{data['sent']}/{data['count']}"
                    if data['count'] else f"{data['sent']}/∞"
                )
                text += (
                    f"  📝 `{ts_id}` ▸ کلمه: "
                    f"`{data['keyword']}` "
                    f"→ `{data['text'][:20]}` ({count})\n"
                )

        return text