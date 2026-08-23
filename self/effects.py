"""
ماژول افکت‌های متنی - نسخه کامل و اصلاح شده
سازگار با فارسی، انگلیسی و متن مخلوط
"""

import asyncio
import time


# ═══════════════════════════════════════
# نگاشت فونت‌های انگلیسی
# ═══════════════════════════════════════

BOLD_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789",
    "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
)

ITALIC_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍"
    "𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧"
)

BOLD_ITALIC_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁"
    "𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛"
)

MONOSPACE_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789",
    "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉"
    "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"
    "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"
)

UPSIDE_DOWN_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789.,!?",
    "∀qƆpƎℲפHIſʞ˥WNOԀQɹS┴∩ΛMX⅄Z"
    "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz"
    "0ƖᄅƐㄣϛ9ㄥ86˙'¡¿"
)

SCRIPT_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵"
    "𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"
)

DOUBLE_STRUCK_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789",
    "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ"
    "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"
    "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"
)


AVAILABLE_EFFECTS = {
    "بولد": "bold",
    "کج": "italic",
    "بولد کج": "bold_italic",
    "زیرخط": "underline",
    "خط خورده": "strike",
    "وارونه": "upside_down",
    "تدریجی": "gradual",
    "منشن": "mention",
    "اسپویلر": "spoiler",
    "کد": "monospace",
    "نقل قول": "quote",
    "اسکریپت": "script",
    "دوخط": "double_struck",
    "معکوس": "reverse",
    "فاصله": "spaced",
}

HTML_ONLY_EFFECTS = {
    "underline", "strike", "spoiler", "quote", "mention"
}


def apply_unicode_transform(text, effect_key):
    if effect_key == "bold":
        return text.translate(BOLD_MAP)
    elif effect_key == "italic":
        return text.translate(ITALIC_MAP)
    elif effect_key == "bold_italic":
        return text.translate(BOLD_ITALIC_MAP)
    elif effect_key == "monospace":
        return text.translate(MONOSPACE_MAP)
    elif effect_key == "upside_down":
        return text.translate(UPSIDE_DOWN_MAP)[::-1]
    elif effect_key == "script":
        return text.translate(SCRIPT_MAP)
    elif effect_key == "double_struck":
        return text.translate(DOUBLE_STRUCK_MAP)
    return text


def apply_string_transform(text, effect_key):
    if effect_key == "reverse":
        return text[::-1]
    elif effect_key == "spaced":
        return " ".join(text)
    return text


def has_persian(text):
    for ch in text:
        if '\u0600' <= ch <= '\u06FF':
            return True
        if '\uFB50' <= ch <= '\uFDFF':
            return True
    return False


def has_english(text):
    for ch in text:
        if 'a' <= ch.lower() <= 'z':
            return True
    return False


def escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def apply_gradual_effect(event, final_text, delay=0.3):
    if not final_text:
        return
    try:
        for i in range(1, len(final_text) + 1):
            partial = final_text[:i]
            try:
                await event.edit(partial)
            except Exception:
                pass
            await asyncio.sleep(delay)
    except Exception as e:
        print(f"⚠️ خطا در تدریجی: {e}")
        try:
            await event.edit(final_text)
        except:
            pass


def _is_only_emoji(text):
    """بررسی اینکه متن فقط ایموجی باشد"""
    if not text:
        return True
    for ch in text:
        if ch in (' ', '\t', '\n', '\r'):
            continue
        if 'a' <= ch.lower() <= 'z':
            return False
        if '\u0600' <= ch <= '\u06FF':
            return False
        if '\uFB50' <= ch <= '\uFDFF':
            return False
        if '\u06F0' <= ch <= '\u06F9':
            return False
        if '0' <= ch <= '9':
            return False
        if ch in '.,:;!?؟؛،()[]{}+-=/<>@#$%^&*\\|~`"\'"':
            return False
    return True


class EffectManager:
    def __init__(self, client, config_manager):
        self.client = client
        self.config = config_manager
        self.last_edit_time = 0
        self.min_delay = 0.5
        self._lock = asyncio.Lock()
        self._processing = set()

    async def _rate_limit(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_edit_time
            if elapsed < self.min_delay:
                await asyncio.sleep(self.min_delay - elapsed)
            self.last_edit_time = time.time()

    def get_active_effects(self):
        return self.config.get("active_effects", [])

    def set_effect(self, effect_name, state):
        effect_key = AVAILABLE_EFFECTS.get(effect_name)
        if not effect_key:
            return f"❌ افکت `{effect_name}` وجود ندارد"

        active = self.config.get("active_effects", [])

        if state:
            if effect_key not in active:
                active.append(effect_key)
                self.config.set("active_effects", active)
            return f"🟢 افکت **{effect_name}** روشن شد"
        else:
            if effect_key in active:
                active.remove(effect_key)
                self.config.set("active_effects", active)
            return f"🔴 افکت **{effect_name}** خاموش شد"

    def clear_all(self):
        self.config.set("active_effects", [])
        return "🗑 همه افکت‌ها خاموش شدند"

    def get_list_text(self):
        active = self.config.get("active_effects", [])
        text = "🎨 **لیست افکت‌های متن:**\n\n"
        for name_fa, key in AVAILABLE_EFFECTS.items():
            status = "🟢" if key in active else "🔴"
            text += f"  {status} {name_fa}\n"
        text += "\n**دستورات:**\n"
        text += "`افکت [نام] روشن`\n"
        text += "`افکت [نام] خاموش`\n"
        text += "`پاکسازی افکت`"
        return text

    async def apply_effects(self, event):
        text = event.raw_text
        if not text:
            return

        if _is_only_emoji(text):
            return

        msg_key = (event.chat_id, event.id)
        if msg_key in self._processing:
            return
        self._processing.add(msg_key)

        try:
            active = self.config.get("active_effects", [])
            if not active:
                return

            print(
                f"🎨 اعمال افکت‌های {active} روی: "
                f"{text[:50]}"
            )

            if "gradual" in active:
                processed = self._process_text(text, active)
                if processed == text:
                    return
                await self._rate_limit()
                await apply_gradual_effect(event, processed)
                return

            processed, use_html = self._process_text_full(
                text, active
            )

            if not use_html and processed == text:
                return

            await self._rate_limit()

            try:
                if use_html:
                    await event.edit(
                        processed, parse_mode='html'
                    )
                else:
                    await event.edit(processed)
                print(f"✅ افکت اعمال شد")
            except Exception as e:
                error_str = str(e)
                if "MESSAGE_NOT_MODIFIED" in error_str:
                    return
                print(
                    f"⚠️ خطا در ویرایش: {error_str[:100]}"
                )
                if use_html:
                    try:
                        fallback, _ = self._process_text_full(
                            text, active, force_no_html=True
                        )
                        if fallback != text:
                            await event.edit(fallback)
                    except:
                        pass

        except Exception as e:
            print(f"⚠️ خطا کلی افکت: {str(e)[:100]}")
        finally:
            asyncio.ensure_future(self._cleanup(msg_key))

    def _process_text(self, text, active):
        """پردازش متن بدون HTML"""
        processed = text

        font_priority = [
            "bold_italic", "bold", "italic",
            "monospace", "script", "double_struck"
        ]
        selected_font = None
        for eff in font_priority:
            if eff in active:
                selected_font = eff
                break

        if ("bold" in active and "italic" in active
                and "bold_italic" not in active):
            selected_font = "bold_italic"

        if selected_font:
            processed = apply_unicode_transform(
                processed, selected_font
            )

        if "upside_down" in active:
            processed = apply_unicode_transform(
                processed, "upside_down"
            )

        if "reverse" in active:
            processed = apply_string_transform(
                processed, "reverse"
            )

        if "spaced" in active:
            processed = apply_string_transform(
                processed, "spaced"
            )

        if "strike" in active:
            processed = "".join(
                c + "\u0336" for c in processed
            )

        if "underline" in active:
            processed = "".join(
                c + "\u0332" for c in processed
            )

        return processed

    def _process_text_full(self, text, active,
                           force_no_html=False):
        """پردازش کامل با تشخیص HTML"""
        processed = text

        font_priority = [
            "bold_italic", "bold", "italic",
            "monospace", "script", "double_struck"
        ]
        selected_font = None
        for eff in font_priority:
            if eff in active:
                selected_font = eff
                break

        if ("bold" in active and "italic" in active
                and "bold_italic" not in active):
            selected_font = "bold_italic"

        text_has_persian = has_persian(processed)

        need_html = False

        if force_no_html:
            need_html = False
        else:
            for eff in HTML_ONLY_EFFECTS:
                if eff in active:
                    need_html = True
                    break

            if selected_font and text_has_persian:
                if selected_font in (
                    "bold", "italic",
                    "bold_italic", "monospace"
                ):
                    need_html = True

        if not need_html:
            if selected_font:
                processed = apply_unicode_transform(
                    processed, selected_font
                )

            if "upside_down" in active:
                processed = apply_unicode_transform(
                    processed, "upside_down"
                )

            if "reverse" in active:
                processed = apply_string_transform(
                    processed, "reverse"
                )

            if "spaced" in active:
                processed = apply_string_transform(
                    processed, "spaced"
                )

            if "strike" in active:
                processed = "".join(
                    c + "\u0336" for c in processed
                )

            if "underline" in active:
                processed = "".join(
                    c + "\u0332" for c in processed
                )

            return processed, False

        if "upside_down" in active:
            processed = apply_unicode_transform(
                processed, "upside_down"
            )

        if "reverse" in active:
            processed = apply_string_transform(
                processed, "reverse"
            )

        if "spaced" in active:
            processed = apply_string_transform(
                processed, "spaced"
            )

        processed = escape_html(processed)

        if selected_font:
            if selected_font == "bold":
                processed = f"<b>{processed}</b>"
            elif selected_font == "italic":
                processed = f"<i>{processed}</i>"
            elif selected_font == "bold_italic":
                processed = f"<b><i>{processed}</i></b>"
            elif selected_font == "monospace":
                processed = f"<code>{processed}</code>"

        if "underline" in active:
            processed = f"<u>{processed}</u>"

        if "strike" in active:
            processed = f"<s>{processed}</s>"

        if "spoiler" in active:
            processed = (
                f"<tg-spoiler>{processed}</tg-spoiler>"
            )

        if "quote" in active:
            processed = (
                f"<blockquote>{processed}</blockquote>"
            )

        if "mention" in active:
            owner_id = self.config.get("owner_id", 0)
            if owner_id:
                processed = (
                    f'<a href="tg://user?id={owner_id}">'
                    f'{processed}</a>'
                )

        return processed, True

    async def _cleanup(self, msg_key):
        await asyncio.sleep(5)
        self._processing.discard(msg_key)