"""
ربات اینلاین - پنل مدیریت
نسخه بروزرسانی شده با اکشن + راهنما
"""

from telethon import events, Button
from panel import (
    set_bot_username,
    get_main_panel_text, get_main_panel_buttons,
    get_clock_panel_text, get_clock_panel_buttons,
    get_react_panel_text, get_react_panel_buttons,
    get_tapchi_panel_text, get_tapchi_panel_buttons,
    get_effects_panel_text, get_effects_panel_buttons,
    get_spam_panel_text, get_spam_panel_buttons,
    get_font_panel_text, get_font_panel_buttons,
    get_action_panel_text, get_action_panel_buttons,
    get_help_panel_text, get_help_panel_buttons,
    get_werewolf_panel_text, get_werewolf_panel_buttons,
    get_werewolf_votes_text, get_werewolf_votes_buttons,  # اضافه شد
    HELP_TEXTS,
)


class BotManager:
    def __init__(self, bot_client, config_manager, clock_mgr, react_mgr,
                 banner_mgr, spam_mgr, panel_tracker, owner_id,
                 action_mgr=None, werewolf_mgr=None):
        self.bot = bot_client
        self.config = config_manager
        self.clock = clock_mgr
        self.react = react_mgr
        self.banner = banner_mgr
        self.spam = spam_mgr
        self.tracker = panel_tracker
        self.owner_id = owner_id
        self.action = action_mgr
        self.werewolf = werewolf_mgr
        self.register_handlers()

    def register_handlers(self):

        @self.bot.on(events.InlineQuery())
        async def inline_handler(event):
            if event.sender_id != self.owner_id:
                await event.answer(
                    [],
                    switch_pm="⛔ فقط صاحب ربات",
                    switch_pm_param="unauthorized"
                )
                return

            builder = event.builder
            result = builder.article(
                title="🛡 پنل مدیریت پیشرفته",
                description="کلیک کنید",
                text=get_main_panel_text(),
                buttons=get_main_panel_buttons(),
            )
            await event.answer([result], cache_time=0, private=True)

        @self.bot.on(events.CallbackQuery())
        async def callback_handler(event):
            if event.sender_id != self.owner_id:
                await event.answer("⛔ دسترسی مجاز نیست!", alert=True)
                return

            data = event.data.decode("utf-8")

            async def safe_edit(text, buttons=None):
                """ویرایش امن بدون خطر کرش در صورت عدم تغییر پیام"""
                try:
                    await event.edit(text, buttons=buttons)
                except Exception as edit_err:
                    if "MESSAGE_NOT_MODIFIED" not in str(edit_err).upper():
                        print(f"❌ خطا در ویرایش پنل: {edit_err}")
                try:
                    await event.answer()
                except:
                    pass

            # ─── منوی اصلی ───
            if data == "panel_main":
                await safe_edit(
                    get_main_panel_text(),
                    buttons=get_main_panel_buttons()
                )


            # ─── پنل گرگینه (اصلی) ───

            elif data == "panel_werewolf" and self.werewolf:

                await safe_edit(

                    get_werewolf_panel_text(self.werewolf),

                    buttons=get_werewolf_panel_buttons(self.werewolf)

                )


            # ─── روشن/خاموش کردن گروه ───

            elif data.startswith("wg_toggle_") and self.werewolf:

                try:

                    gid = int(data[10:])

                except ValueError:

                    return

                state = self.werewolf.games.get(gid)

                if state:

                    current = state.get("enabled", True)

                    state["enabled"] = not current

                    self.werewolf._save_games()

                    status = "خاموش 🔴" if current else "روشن 🟢"

                    name = state.get("group_name", str(gid))

                    await event.answer(f"{name}: {status}", alert=True)

                else:

                    await event.answer("❌ گروه پیدا نشد", alert=True)

                await safe_edit(

                    get_werewolf_panel_text(self.werewolf),

                    buttons=get_werewolf_panel_buttons(self.werewolf)

                )


            # ─── حذف گروه ───

            elif data.startswith("wg_delete_") and self.werewolf:

                try:

                    gid = int(data[10:])

                except ValueError:

                    return

                state = self.werewolf.games.get(gid)

                if state:

                    name = state.get("group_name", str(gid))

                    await safe_edit(

                        f"⚠️ **حذف گروه {name}؟**\n"

                        "تمام رأی‌های این گروه هم حذف می‌شوند.",

                        buttons=[

                            [Button.inline(

                                "✅ بله، حذف کن",

                                data=f"wg_confirm_del_{gid}"

                            )],

                            [Button.inline(

                                "🔙 انصراف",

                                data="panel_werewolf"

                            )],

                        ]

                    )

                else:

                    await event.answer("❌ گروه پیدا نشد", alert=True)

                    await safe_edit(

                        get_werewolf_panel_text(self.werewolf),

                        buttons=get_werewolf_panel_buttons(self.werewolf)

                    )


            elif data.startswith("wg_confirm_del_") and self.werewolf:

                try:

                    gid = int(data[15:])

                except ValueError:

                    return

                result = self.werewolf.untrack_group(gid)

                await event.answer(result, alert=True)

                await safe_edit(

                    get_werewolf_panel_text(self.werewolf),

                    buttons=get_werewolf_panel_buttons(self.werewolf)

                )


            # ─── صفحه رأی‌ها ───

            elif data == "werewolf_votes" and self.werewolf:

                await safe_edit(

                    get_werewolf_votes_text(self.werewolf),

                    buttons=get_werewolf_votes_buttons(self.werewolf)

                )


            elif data == "werewolf_vote_toggle" and self.werewolf:

                if self.werewolf.is_vote_enabled():

                    result = self.werewolf.disable_votes()

                else:

                    result = self.werewolf.enable_votes()

                await event.answer(result, alert=True)

                await safe_edit(

                    get_werewolf_votes_text(self.werewolf),

                    buttons=get_werewolf_votes_buttons(self.werewolf)

                )


            elif data == "werewolf_vote_clear" and self.werewolf:

                self.werewolf.clear_votes()

                await event.answer("🗑 همه رأی‌ها پاک شدند.", alert=True)

                await safe_edit(

                    get_werewolf_votes_text(self.werewolf),

                    buttons=get_werewolf_votes_buttons(self.werewolf)

                )


            # ─── راهنما ───

            elif data == "werewolf_help" and self.werewolf:

                await safe_edit(

                    self.werewolf.get_help_text(),

                    buttons=[

                        [Button.inline(

                            "🔙 بازگشت", data="panel_werewolf"

                        )]

                    ]

                )

            elif data == "panel_close":
                try:
                    msg_id = event.message_id
                    chat_id = (
                        event.chat_id
                        if event.chat_id
                        else event.message.peer_id
                    )
                    self.tracker.remove_panel(chat_id, msg_id)
                    await event.delete()
                except Exception:
                    try:
                        await event.edit("✅ پنل بسته شد.")
                    except:
                        pass

            # ─── پنل ساعت ───
            elif data == "panel_clock":
                await safe_edit(
                    get_clock_panel_text(self.config),
                    buttons=get_clock_panel_buttons(self.config)
                )

            elif data == "clock_toggle":
                current = self.config.get("clock_enabled")
                self.config.set("clock_enabled", not current)
                if not current:
                    self.clock.start()
                    await event.answer(
                        "✅ ساعت روشن شد!", alert=True
                    )
                else:
                    self.clock.stop()
                    await event.answer(
                        "🔴 ساعت خاموش شد!", alert=True
                    )
                await safe_edit(
                    get_clock_panel_text(self.config),
                    buttons=get_clock_panel_buttons(self.config)
                )

            elif data == "bio_toggle":
                if not self.config.get("bio_text"):
                    await event.answer(
                        "❌ ابتدا با 'بیو [متن]' متن بیو را تنظیم کنید!",
                        alert=True
                    )
                    return
                current = self.config.get("clock_bio_enabled")
                self.config.set("clock_bio_enabled", not current)
                await event.answer(
                    "✅ ساعت بیو روشن شد!"
                    if not current
                    else "🔴 ساعت بیو خاموش شد!",
                    alert=True
                )
                await safe_edit(
                    get_clock_panel_text(self.config),
                    buttons=get_clock_panel_buttons(self.config)
                )

            # ─── پنل ریکت ───
            elif data == "panel_react":
                await safe_edit(
                    get_react_panel_text(self.config),
                    buttons=get_react_panel_buttons()
                )

            elif data == "react_list":
                text = self.react.get_full_list()
                await safe_edit(
                    text,
                    buttons=[
                        [Button.inline(
                            "🔙 بازگشت", data="panel_react"
                        )]
                    ]
                )

            elif data == "react_clear":
                await safe_edit(
                    "⚠️ **آیا مطمئنید؟**\n"
                    "همه ریکت‌ها حذف می‌شوند.",
                    buttons=[
                        [Button.inline(
                            "✅ بله", data="react_clear_confirm"
                        )],
                        [Button.inline(
                            "🔙 انصراف", data="panel_react"
                        )],
                    ]
                )

            elif data == "react_clear_confirm":
                result = self.react.clear_all()
                await event.answer(result, alert=True)
                await safe_edit(
                    get_react_panel_text(self.config),
                    buttons=get_react_panel_buttons()
                )

            # ─── پنل تپچی ───
            elif data == "panel_tapchi":
                await safe_edit(
                    get_tapchi_panel_text(self.config, self.banner),
                    buttons=get_tapchi_panel_buttons(self.config)
                )

            elif data == "tapchi_toggle":
                if self.config.get("tapchi_enabled"):
                    result = self.banner.disable()
                else:
                    result = self.banner.enable()
                await event.answer(
                    result.split('\n')[0], alert=True
                )
                await safe_edit(
                    get_tapchi_panel_text(self.config, self.banner),
                    buttons=get_tapchi_panel_buttons(self.config)
                )

            elif data == "tapchi_mode_forward":
                self.banner.set_mode("forward")
                await event.answer(
                    "✅ حالت: فوروارد", alert=True
                )
                await safe_edit(
                    get_tapchi_panel_text(self.config, self.banner),
                    buttons=get_tapchi_panel_buttons(self.config)
                )

            elif data == "tapchi_mode_copy":
                self.banner.set_mode("copy")
                await event.answer(
                    "✅ حالت: کپی", alert=True
                )
                await safe_edit(
                    get_tapchi_panel_text(self.config, self.banner),
                    buttons=get_tapchi_panel_buttons(self.config)
                )

            elif data == "tapchi_list":
                text = self.banner.get_full_list()
                await safe_edit(
                    text,
                    buttons=[
                        [Button.inline(
                            "🔙 بازگشت", data="panel_tapchi"
                        )]
                    ]
                )

            elif data == "tapchi_clear":
                await safe_edit(
                    "⚠️ **آیا مطمئنید؟**\n"
                    "همه بنرها حذف می‌شوند.",
                    buttons=[
                        [Button.inline(
                            "✅ بله",
                            data="tapchi_clear_confirm"
                        )],
                        [Button.inline(
                            "🔙 انصراف", data="panel_tapchi"
                        )],
                    ]
                )

            elif data == "tapchi_clear_confirm":
                result = self.banner.clear_all_banners()
                await event.answer(result, alert=True)
                await safe_edit(
                    get_tapchi_panel_text(self.config, self.banner),
                    buttons=get_tapchi_panel_buttons(self.config)
                )

            # ─── پنل افکت ───
            elif data == "panel_effects":
                await safe_edit(
                    get_effects_panel_text(self.config),
                    buttons=get_effects_panel_buttons(self.config)
                )

            elif data.startswith("eff_") and data != "eff_clear":
                effect_key = data[4:]
                from effects import AVAILABLE_EFFECTS
                name_fa = None
                for fa, key in AVAILABLE_EFFECTS.items():
                    if key == effect_key:
                        name_fa = fa
                        break

                if name_fa:
                    active = self.config.get("active_effects", [])
                    if effect_key in active:
                        active.remove(effect_key)
                        await event.answer(
                            f"🔴 {name_fa} خاموش شد"
                        )
                    else:
                        active.append(effect_key)
                        await event.answer(
                            f"🟢 {name_fa} روشن شد"
                        )
                    self.config.set("active_effects", active)

                    await safe_edit(
                        get_effects_panel_text(self.config),
                        buttons=get_effects_panel_buttons(
                            self.config
                        )
                    )

            elif data == "eff_clear":
                self.config.set("active_effects", [])
                await event.answer(
                    "🗑 همه افکت‌ها پاک شدند", alert=True
                )
                await safe_edit(
                    get_effects_panel_text(self.config),
                    buttons=get_effects_panel_buttons(self.config)
                )

            # ─── پنل اسپم ───
            elif data == "panel_spam":
                await safe_edit(
                    get_spam_panel_text(self.spam),
                    buttons=get_spam_panel_buttons()
                )

            elif data == "spam_list":
                text = self.spam.get_full_status_text()
                await safe_edit(
                    text,
                    buttons=[
                        [Button.inline(
                            "🔙 بازگشت", data="panel_spam"
                        )]
                    ]
                )

            elif data == "spam_stop_all":
                await safe_edit(
                    "⚠️ **آیا مطمئنید؟**\n"
                    "همه اسپم‌ها متوقف می‌شوند.",
                    buttons=[
                        [Button.inline(
                            "✅ بله",
                            data="spam_stop_confirm"
                        )],
                        [Button.inline(
                            "🔙 انصراف", data="panel_spam"
                        )],
                    ]
                )

            elif data == "spam_stop_confirm":
                total = self.spam.stop_all()
                await event.answer(
                    f"🛑 {total} اسپم متوقف شد", alert=True
                )
                await safe_edit(
                    get_spam_panel_text(self.spam),
                    buttons=get_spam_panel_buttons()
                )

            # ─── پنل اکشن ───
            elif data == "panel_action":
                await safe_edit(
                    get_action_panel_text(self.config),
                    buttons=get_action_panel_buttons(self.config)
                )

            elif data.startswith("act_toggle_"):
                try:
                    await event.answer()
                except:
                    pass

                chat_id_str = data[11:]
                try:
                    target_chat_id = int(chat_id_str)
                except ValueError:
                    return

                if self.action:
                    action_data = self.action._find_action(
                        target_chat_id
                    )
                    if action_data:
                        try:
                            if action_data.get("enabled", True):
                                self.action.disable_action(
                                    target_chat_id
                                )
                            else:
                                self.action.enable_action(
                                    target_chat_id
                                )
                        except Exception as e:
                            print(
                                f"❌ خطا در toggle اکشن: {e}"
                            )

                await safe_edit(
                    get_action_panel_text(self.config),
                    buttons=get_action_panel_buttons(
                        self.config
                    )
                )

            elif data == "action_list":
                if self.action:
                    text = self.action.get_list_text()
                else:
                    text = "❌ ماژول اکشن فعال نیست"
                await safe_edit(
                    text,
                    buttons=[
                        [Button.inline(
                            "🔙 بازگشت", data="panel_action"
                        )]
                    ]
                )

            elif data == "action_clear":
                await safe_edit(
                    "⚠️ **آیا مطمئنید؟**\n"
                    "همه اکشن‌ها حذف می‌شوند.",
                    buttons=[
                        [Button.inline(
                            "✅ بله",
                            data="action_clear_confirm"
                        )],
                        [Button.inline(
                            "🔙 انصراف",
                            data="panel_action"
                        )],
                    ]
                )

            elif data == "action_clear_confirm":
                if self.action:
                    result = self.action.clear_all()
                    await event.answer(result, alert=True)
                await safe_edit(
                    get_action_panel_text(self.config),
                    buttons=get_action_panel_buttons(self.config)
                )

            # ─── پنل فونت ───
            elif data == "panel_font":
                await safe_edit(
                    get_font_panel_text(),
                    buttons=get_font_panel_buttons()
                )

            elif data.startswith("font_"):
                try:
                    font_id = int(data.split("_")[1])
                    self.config.set("clock_font", font_id)
                    self.clock.last_time = ""
                    await event.answer(
                        f"✅ فونت {font_id} انتخاب شد!",
                        alert=True
                    )
                except (IndexError, ValueError):
                    await event.answer("❌ خطا در تغییر فونت", alert=True)

                await safe_edit(
                    get_font_panel_text(),
                    buttons=get_font_panel_buttons()
                )

            # ─── پنل راهنما ───
            elif data == "panel_help":
                await safe_edit(
                    get_help_panel_text(),
                    buttons=get_help_panel_buttons()
                )

            elif data.startswith("help_"):
                help_text = HELP_TEXTS.get(data, "❌ یافت نشد")
                await safe_edit(
                    help_text,
                    buttons=[
                        [Button.inline(
                            "🔙 راهنما", data="panel_help"
                        )],
                        [Button.inline(
                            "🔙 منو", data="panel_main"
                        )],
                    ]
                )