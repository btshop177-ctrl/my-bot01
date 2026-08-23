import asyncio
import logging
import re

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

from config import (
    BOT_TOKEN, ADMIN_IDS, COIN_NAME,
    MIN_BET, MAX_BET, MIN_WITHDRAW,
    PROXY_URL, PROXY_SOCKS5_URL,
    BROADCAST_DELAY, HOUSE_FEE, BSLIFE_OUR_NAME,
)
from database import Database
from keyboards import (
    Btn, CANCEL_TEXTS,
    user_menu, account_menu, admin_menu,
    channel_menu, user_mgmt_menu, admin_mgmt_menu, treasury_menu,
    cancel_keyboard, remove_keyboard,
    join_channels_keyboard, upcoming_matches_inline,
    prediction_inline, bet_amount_inline, confirm_bet_inline,
    admin_matches_inline, admin_match_actions, result_inline,
    users_list_inline, user_detail_inline,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

try:
    db = Database()
except Exception as e:
    logger.critical(f"DB failed: {e}")
    raise SystemExit(1)


def is_admin(uid):
    return uid in ADMIN_IDS or db.is_admin(uid)


async def check_join(uid, ctx):
    channels = db.get_channels()
    not_joined = []
    for ch in channels:
        try:
            member = await ctx.bot.get_chat_member(ch["channel_identifier"], uid)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append(ch)
        except TelegramError:
            continue
    return len(not_joined) == 0, not_joined


def validate_special_name(name):
    name = name.strip()
    if not re.fullmatch(r'[A-Za-z]{3,16}', name):
        return None
    return name[0].upper() + name[1:].lower()


def is_private(update):
    return update.effective_chat and update.effective_chat.type == "private"


def get_menu(uid):
    return admin_menu() if is_admin(uid) else user_menu()


# ═══════════════════════════════════
#            /start
# ═══════════════════════════════════
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    user = update.effective_user
    uid = user.id
    db.ensure_user(uid, user.username, user.first_name, user.last_name)
    ctx.user_data.clear()

    if is_admin(uid):
        await update.message.reply_text(
            f"👑 **پنل مدیریت**\n💰 موجودی: **{db.get_coins(uid)}** {COIN_NAME}",
            parse_mode="Markdown", reply_markup=admin_menu())
        return

    if db.is_banned(uid):
        await update.message.reply_text("⛔ حساب شما مسدود شده است.")
        return

    ok, nj = await check_join(uid, ctx)
    if not ok:
        txt = ("⚠️ **ابتدا عضو کانال‌های زیر شوید:**\n\n"
               + "\n".join(f"📢 {ch['channel_title'] or ch['channel_identifier']}" for ch in nj)
               + "\n\nسپس ✅ عضو شدم را بزنید.")
        await update.message.reply_text(txt, parse_mode="Markdown",
                                        reply_markup=join_channels_keyboard(nj))
        return

    if not db.has_special_name(uid):
        ctx.user_data["state"] = "set_special_name"
        await update.message.reply_text(
            "✨ **انتخاب اسم خاص**\n\n"
            "• فقط **حروف انگلیسی** (A-Z)\n• **۳ تا ۱۶** حرف\n"
            "• بدون عدد/فاصله/کاراکتر\n\nمثال: `Mori` | `Ali` | `Sarina`",
            parse_mode="Markdown", reply_markup=remove_keyboard())
        return

    sn = db.get_special_name(uid)
    coins = db.get_coins(uid)
    await update.message.reply_text(
        f"🎯 خوش اومدی **{sn}**! ⚽\n💰 موجودی: **{coins}** {COIN_NAME}",
        parse_mode="Markdown", reply_markup=user_menu())


async def cancel_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    ctx.user_data.clear()
    if not db.has_special_name(uid) and not is_admin(uid):
        ctx.user_data["state"] = "set_special_name"
        await update.message.reply_text(
            "❌ **باید** اسم خاص انتخاب کنید:",
            parse_mode="Markdown", reply_markup=remove_keyboard())
        return
    await update.message.reply_text("❌ لغو شد.", reply_markup=get_menu(uid))


# ═══════════════════════════════════
#        CALLBACK HANDLER
# ═══════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = update.effective_user.id
    data = q.data

    # ── چک عضویت ──
    if data == "check_join":
        ok, nj = await check_join(uid, ctx)
        if not ok:
            await q.answer("🔔 هنوز عضو نشدید!", show_alert=True)
            return
        await q.answer("✅ عضویت تایید شد!")
        if not db.has_special_name(uid):
            await q.edit_message_text(
                "✅ عضویت تایید شد!\n\n✨ **اسم خاص** انتخاب کنید:\nمثال: `Mori`",
                parse_mode="Markdown")
            ctx.user_data["state"] = "set_special_name"
        else:
            sn = db.get_special_name(uid)
            coins = db.get_coins(uid)
            await q.edit_message_text(
                f"✅ تایید!\n👤 **{sn}** | 💰 **{coins}** {COIN_NAME}",
                parse_mode="Markdown")
            await q.message.reply_text("⚽", reply_markup=user_menu())
        return

    await q.answer()

    # ── بازگشت مسابقات ──
    if data == "back_matches":
        matches = db.get_upcoming_matches()
        if not matches:
            await q.edit_message_text("📭 مسابقه‌ای نیست.")
            return
        try:
            await q.edit_message_text("⚽ **مسابقات پیش‌رو:**", parse_mode="Markdown",
                                      reply_markup=upcoming_matches_inline(matches))
        except TelegramError:
            await q.message.reply_text("⚽ **مسابقات پیش‌رو:**", parse_mode="Markdown",
                                       reply_markup=upcoming_matches_inline(matches))
        return

    # ── لغو شرط کاربر ──
    if data.startswith("cancelbet_"):
        mid = int(data.split("_")[1])
        success, text = db.cancel_prediction(uid, mid)
        if success:
            db.log_activity(uid, "cancel_bet", f"#{mid}")
            await q.edit_message_text(text, parse_mode="Markdown")
            m = db.get_match(mid)
            if m and m["status"] == "upcoming":
                await q.message.reply_text(
                    f"⚽ **مسابقه #{mid}**\n📝 {m['caption']}\n📅 {m['deadline']}\n\n"
                    f"👇 شرط جدید بذارید:",
                    parse_mode="Markdown",
                    reply_markup=prediction_inline(m, has_existing_bet=False))
        else:
            await q.answer(text, show_alert=True)
        return

    # ── مسابقه ──
    if data.startswith("match_"):
        mid = int(data.split("_")[1])
        m = db.get_match(mid)
        if not m or m["status"] != "upcoming":
            await q.edit_message_text("❌ این مسابقه در دسترس نیست.")
            return
        existing = db.get_user_prediction_for_match(uid, mid)
        has_bet = existing is not None
        txt = f"⚽ **مسابقه #{mid}**\n\n📝 {m['caption']}\n📅 مهلت: {m['deadline']}\n\n"
        if has_bet:
            option_map = {"option_1": m["option_1"], "option_2": m["option_2"], "option_3": m["option_3"]}
            old_option = option_map.get(existing["prediction"], "?")
            txt += (f"⚠️ **شرط فعلی شما:**\n🎯 {old_option} | 💰 {existing['coins_bet']} {COIN_NAME}\n\n"
                    f"برای تغییر، ابتدا شرط را لغو کنید:")
        else:
            txt += "👇 پیش‌بینی خود را انتخاب کنید:"
        if m["photo_id"]:
            try:
                await q.message.delete()
            except TelegramError:
                pass
            await ctx.bot.send_photo(chat_id=q.message.chat_id, photo=m["photo_id"],
                                     caption=txt, parse_mode="Markdown",
                                     reply_markup=prediction_inline(m, has_existing_bet=has_bet))
        else:
            try:
                await q.edit_message_text(txt, parse_mode="Markdown",
                                          reply_markup=prediction_inline(m, has_existing_bet=has_bet))
            except TelegramError:
                await q.message.reply_text(txt, parse_mode="Markdown",
                                           reply_markup=prediction_inline(m, has_existing_bet=has_bet))
        return

    # ── پیش‌بینی ──
    if data.startswith("pred_"):
        parts = data.split("_")
        mid = int(parts[1])
        prediction = parts[2] + "_" + parts[3]
        m = db.get_match(mid)
        if not m or m["status"] != "upcoming":
            await q.edit_message_text("❌ مسابقه در دسترس نیست.")
            return
        existing = db.get_user_prediction_for_match(uid, mid)
        if existing:
            option_map = {"option_1": m["option_1"], "option_2": m["option_2"], "option_3": m["option_3"]}
            old_option = option_map.get(existing["prediction"], "?")
            await q.answer(
                f"⚠️ قبلاً شرط بسته‌اید!\n🎯 {old_option} | 💰 {existing['coins_bet']}\n"
                f"ابتدا لغو کنید.", show_alert=True)
            return
        option_text = m[prediction]
        try:
            await q.edit_message_text(
                f"🎯 **{option_text}**\n⚽ {m['caption'][:80]}\n\n💰 مبلغ شرط:",
                parse_mode="Markdown", reply_markup=bet_amount_inline(mid, prediction))
        except TelegramError:
            await q.message.reply_text(
                f"🎯 **{option_text}**\n💰 مبلغ شرط:",
                parse_mode="Markdown", reply_markup=bet_amount_inline(mid, prediction))
        return

    # ── مبلغ دلخواه ──
    if data.startswith("betcustom_"):
        parts = data.split("_")
        mid = int(parts[1])
        prediction = parts[2] + "_" + parts[3]
        ctx.user_data["state"] = "custom_bet"
        ctx.user_data["bet_match"] = mid
        ctx.user_data["bet_pred"] = prediction
        await q.edit_message_text(
            f"✏️ مبلغ شرط:\nحداقل: {MIN_BET} | حداکثر: {MAX_BET}\n\n/cancel")
        return

    # ── مبلغ شرط ──
    if data.startswith("bet_"):
        parts = data.split("_")
        mid = int(parts[1])
        prediction = parts[2] + "_" + parts[3]
        amount = int(parts[4])
        m = db.get_match(mid)
        if not m:
            await q.edit_message_text("❌ مسابقه نیست.")
            return
        option_text = m[prediction]
        coins = db.get_coins(uid)
        await q.edit_message_text(
            f"⚠️ **تایید**\n\n⚽ #{mid}\n🎯 {option_text}\n"
            f"💰 {amount} {COIN_NAME}\n💎 {coins} {COIN_NAME}\n\nمطمئنید؟",
            parse_mode="Markdown",
            reply_markup=confirm_bet_inline(mid, prediction, amount, option_text))
        return

    # ── تایید شرط ──
    if data.startswith("confirm_"):
        parts = data.split("_")
        mid = int(parts[1])
        prediction = parts[2] + "_" + parts[3]
        amount = int(parts[4])
        success, text, pid = db.place_prediction(uid, mid, prediction, amount)
        db.log_activity(uid, "bet", f"#{mid} | {prediction} | {amount}")
        await q.edit_message_text(text, parse_mode="Markdown")
        return

    # ── ادمین: لیست مسابقات ──
    if data == "adm_matches_list":
        matches = db.get_all_matches()
        if not matches:
            await q.edit_message_text("📭 مسابقه‌ای نیست.")
            return
        await q.edit_message_text("⚽ **مدیریت مسابقات:**", parse_mode="Markdown",
                                  reply_markup=admin_matches_inline(matches))
        return

    # ── بستن شرط‌بندی (ادمین) ──
    if data.startswith("closebet_"):
        mid = int(data.split("_")[1])
        m = db.get_match(mid)
        if not m or m["status"] != "upcoming":
            await q.edit_message_text("❌ قابل بستن نیست.")
            return
        db.close_match(mid)
        db.log_activity(uid, "close_match", f"#{mid}")
        m = db.get_match(mid)
        preds = db.get_match_predictions(mid)
        await q.edit_message_text(
            f"🔒 **شرط‌بندی #{mid} بسته شد!**\n\n📝 {m['caption'][:100]}\n🎯 {len(preds)} پیش‌بینی",
            parse_mode="Markdown", reply_markup=admin_match_actions(m))
        return

    # ── باز کردن مجدد ──
    if data.startswith("reopenbet_"):
        mid = int(data.split("_")[1])
        m = db.get_match(mid)
        if not m or m["status"] != "closed":
            await q.edit_message_text("❌ قابل باز کردن نیست.")
            return
        db.reopen_match(mid)
        db.log_activity(uid, "reopen_match", f"#{mid}")
        m = db.get_match(mid)
        await q.edit_message_text(
            f"🔓 **شرط‌بندی #{mid} باز شد!**\n\n📝 {m['caption'][:100]}",
            parse_mode="Markdown", reply_markup=admin_match_actions(m))
        return

    # ── ثبت نتیجه ──
    if data.startswith("setresult_"):
        mid = int(data.split("_")[1])
        m = db.get_match(mid)
        if not m or m["status"] not in ("upcoming", "closed"):
            await q.edit_message_text("❌ قابل نتیجه‌گذاری نیست.")
            return
        await q.edit_message_text(
            f"🏁 **ثبت نتیجه #{mid}**\n\n{m['caption'][:100]}\n\nنتیجه:",
            parse_mode="Markdown", reply_markup=result_inline(m))
        return

    # ── پیش‌بینی‌ها ──
    if data.startswith("matchpreds_"):
        mid = int(data.split("_")[1])
        m = db.get_match(mid)
        preds = db.get_match_predictions(mid)
        if not preds:
            await q.answer("📭 پیش‌بینی‌ای نیست.", show_alert=True)
            return
        status_map = {"pending": "⏳", "won": "✅", "lost": "❌"}
        txt = f"📊 **پیش‌بینی‌های #{mid}:**\n\n"
        for p in preds:
            name = p["special_name"] or p["first_name"] or str(p["user_id"])
            opt = m[p["prediction"]] if m and p["prediction"] in ("option_1", "option_2", "option_3") else "?"
            txt += f"• **{name}**: {opt} | 💰{p['coins_bet']} | {status_map.get(p['status'], '?')}\n"
        await q.edit_message_text(txt[:4000], parse_mode="Markdown", reply_markup=admin_match_actions(m))
        return

    # ── جزئیات مسابقه ──
    if data.startswith("adm_match_"):
        mid = int(data.split("_")[2])
        m = db.get_match(mid)
        if not m:
            await q.edit_message_text("❌ نیست.")
            return
        preds = db.get_match_predictions(mid)
        status_text = {"upcoming": "🟡 باز", "closed": "🟠 بسته", "finished": "🟢 تمام"}.get(m["status"], m["status"])
        txt = (f"⚽ **مسابقه #{mid}**\n\n📝 {m['caption'][:100]}\n📅 {m['deadline']}\n"
               f"📊 {status_text}\n🏁 {m['result'] or 'ثبت نشده'}\n🎯 {len(preds)} پیش‌بینی\n\n"
               f"🟠 {m['option_1']}\n🤝 {m['option_2']}\n🟡 {m['option_3']}")
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=admin_match_actions(m))
        return

    # ── نتیجه ──
    if data.startswith("result_"):
        parts = data.split("_")
        mid = int(parts[1])
        result = parts[2] + "_" + parts[3]
        db.set_match_result(mid, result)
        ok, settle_msg = db.settle_match(mid)
        db.log_activity(uid, "set_result", f"#{mid}: {result}")
        await q.edit_message_text(f"✅ نتیجه ثبت شد!\n\n{settle_msg}", parse_mode="Markdown")
        return

    # ── کاربران ──
    if data == "usrlist":
        users = db.get_all_users_for_admin()
        if not users:
            await q.edit_message_text("📭")
            return
        await q.edit_message_text(f"👥 ({len(users)})", parse_mode="Markdown",
                                  reply_markup=users_list_inline(users[:30]))
        return

    if data.startswith("usradd_"):
        tid = int(data.split("_")[1])
        ctx.user_data["state"] = "inline_add_coins"
        ctx.user_data["target_user"] = tid
        u = db.get_user(tid)
        sn = u["special_name"] or u["first_name"] or str(tid) if u else str(tid)
        await q.edit_message_text(
            f"💎 **افزودن سکه**\n👤 **{sn}** (`{tid}`)\n💰 **{u['coins'] if u else 0}**\n\nمقدار:\n/cancel",
            parse_mode="Markdown")
        return

    if data.startswith("usrsub_"):
        tid = int(data.split("_")[1])
        ctx.user_data["state"] = "inline_sub_coins"
        ctx.user_data["target_user"] = tid
        u = db.get_user(tid)
        sn = u["special_name"] or u["first_name"] or str(tid) if u else str(tid)
        await q.edit_message_text(
            f"📤 **کسر سکه**\n👤 **{sn}** (`{tid}`)\n💰 **{u['coins'] if u else 0}**\n\nمقدار:\n/cancel",
            parse_mode="Markdown")
        return

    if data.startswith("usrset_"):
        tid = int(data.split("_")[1])
        ctx.user_data["state"] = "inline_set_coins"
        ctx.user_data["target_user"] = tid
        u = db.get_user(tid)
        sn = u["special_name"] or u["first_name"] or str(tid) if u else str(tid)
        await q.edit_message_text(
            f"💰 **تنظیم سکه**\n👤 **{sn}** (`{tid}`)\n💰 **{u['coins'] if u else 0}**\n\nسکه جدید:\n/cancel",
            parse_mode="Markdown")
        return

    if data.startswith("usrban_"):
        tid = int(data.split("_")[1])
        u = db.get_user(tid)
        if not u:
            await q.answer("❌", show_alert=True)
            return
        if u["is_banned"]:
            db.unban_user(tid)
            await q.answer("✅ آزاد شد", show_alert=True)
        else:
            db.ban_user(tid)
            await q.answer("🚫 بن شد", show_alert=True)
        db.log_activity(uid, "ban", str(tid))
        u = db.get_user(tid)
        sn = u["special_name"] or "ندارد"
        ban_txt = "🚫 بن" if u["is_banned"] else "✅ آزاد"
        await q.edit_message_text(
            f"👤 `{u['user_id']}`\n✨ **{sn}**\n💰 **{u['coins']}**\n{ban_txt}",
            parse_mode="Markdown", reply_markup=user_detail_inline(u))
        return

    if data.startswith("usr_"):
        tid = int(data.split("_")[1])
        u = db.get_user(tid)
        if not u:
            await q.answer("❌", show_alert=True)
            return
        sn = u["special_name"] or "ندارد"
        ban_txt = "🚫 بن" if u["is_banned"] else "✅ آزاد"
        await q.edit_message_text(
            f"👤 `{u['user_id']}` @{u['username'] or '-'}\n👤 {u['first_name'] or '-'}\n"
            f"✨ **{sn}**\n💰 **{u['coins']}**\n🎯 {u['total_bets']} | ✅ {u['total_won']} | ❌ {u['total_lost']}\n{ban_txt}",
            parse_mode="Markdown", reply_markup=user_detail_inline(u))
        return


# ═══════════════════════════════════
#          PHOTO HANDLER
# ═══════════════════════════════════
async def photo_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    state = ctx.user_data.get("state", "")
    if state == "add_match_photo" and update.message.photo:
        ctx.user_data["match_photo"] = update.message.photo[-1].file_id
        ctx.user_data["state"] = "add_match_caption"
        await update.message.reply_text(
            "✅ عکس دریافت شد.\n📝 **متن بازی:**\n\n/cancel",
            parse_mode="Markdown", reply_markup=cancel_keyboard())


# ═══════════════════════════════════
#         MESSAGE HANDLER
# ═══════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    user = update.effective_user
    uid = user.id
    msg = (update.message.text or "").strip()
    state = ctx.user_data.get("state", "")
    admin = is_admin(uid)

    db.ensure_user(uid, user.username, user.first_name, user.last_name)

    if not admin and db.is_banned(uid):
        await update.message.reply_text("⛔ مسدود شده‌اید.")
        return

    if msg in CANCEL_TEXTS:
        if not admin and state in ("set_special_name", "edit_special_name") and not db.has_special_name(uid):
            await update.message.reply_text("❌ **باید** اسم خاص انتخاب کنید:",
                                            parse_mode="Markdown", reply_markup=remove_keyboard())
            return
        ctx.user_data.clear()
        await update.message.reply_text("❌ لغو شد.", reply_markup=get_menu(uid))
        return

    if admin:
        if state:
            await process_state(update, ctx, state, msg, uid, admin)
        else:
            await admin_navigation(update, ctx, uid, msg)
        return

    if state not in ("set_special_name", "edit_special_name"):
        ok, nj = await check_join(uid, ctx)
        if not ok:
            await update.message.reply_text("⚠️ **عضو کانال‌ها شوید!**",
                                            parse_mode="Markdown",
                                            reply_markup=join_channels_keyboard(nj))
            ctx.user_data.clear()
            return

    if state not in ("set_special_name", "edit_special_name") and not db.has_special_name(uid):
        ctx.user_data["state"] = "set_special_name"
        await update.message.reply_text("✨ **اسم خاص انتخاب کنید:**\nمثال: `Mori`",
                                        parse_mode="Markdown", reply_markup=remove_keyboard())
        return

    if state:
        await process_state(update, ctx, state, msg, uid, admin)
        return

    await user_navigation(update, ctx, uid, msg)


# ═══════════════════════════════════
#        ADMIN NAVIGATION
# ═══════════════════════════════════
async def admin_navigation(update, ctx, uid, msg):

    if msg in (Btn.BACK_MAIN, Btn.BACK_ADMIN):
        ctx.user_data.clear()
        await update.message.reply_text(
            f"👑 **پنل مدیریت**\n💰 **{db.get_coins(uid)}** {COIN_NAME}",
            parse_mode="Markdown", reply_markup=admin_menu())
        return

    if msg == Btn.STATS:
        s = db.get_stats()
        await update.message.reply_text(
            f"📊 **آمار**\n\n👥 {s['total_users']}\n🎯 {s['total_predictions']}\n"
            f"💰 {s['total_coins']} {COIN_NAME}\n⚽ {s['active_matches']}\n🏛️ {s['treasury']} {COIN_NAME}",
            parse_mode="Markdown", reply_markup=admin_menu())
        return

    if msg == Btn.ADD_MATCH:
        ctx.user_data["state"] = "add_match_photo"
        await update.message.reply_text("🖼️ عکس ارسال کنید یا `ندارد`\n\n/cancel",
                                        parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if msg == Btn.MANAGE_MATCHES:
        matches = db.get_all_matches()
        if not matches:
            await update.message.reply_text("📭 مسابقه‌ای نیست.", reply_markup=admin_menu())
            return
        await update.message.reply_text("⚽ **مدیریت مسابقات:**", parse_mode="Markdown",
                                        reply_markup=admin_matches_inline(matches))
        return

    if msg == Btn.CHANNELS:
        await update.message.reply_text("📢 کانال‌ها:", reply_markup=channel_menu())
        return

    if msg == Btn.ADD_CHANNEL:
        ctx.user_data["state"] = "add_channel"
        await update.message.reply_text("➕ آیدی یا @یوزرنیم:\n\n/cancel",
                                        parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if msg == Btn.LIST_CHANNELS:
        chs = db.get_channels()
        txt = "📭 کانالی نیست." if not chs else "📢 **کانال‌ها:**\n\n" + "\n".join(
            f"{i}. `{ch['channel_identifier']}` - {ch['channel_title'] or '?'}" for i, ch in enumerate(chs, 1))
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=channel_menu())
        return

    if msg == Btn.DEL_CHANNEL:
        ctx.user_data["state"] = "remove_channel"
        chs = db.get_channels()
        if not chs:
            await update.message.reply_text("📭", reply_markup=channel_menu())
            ctx.user_data.clear()
            return
        txt = "❌ **حذف:**\n\n" + "\n".join(
            f"{i}. `{ch['channel_identifier']}`" for i, ch in enumerate(chs, 1)) + "\n\nشماره:\n/cancel"
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if msg == Btn.USERS:
        users = db.get_all_users_for_admin()
        if not users:
            await update.message.reply_text("📭", reply_markup=admin_menu())
            return
        await update.message.reply_text(f"👥 ({len(users)})", parse_mode="Markdown",
                                        reply_markup=users_list_inline(users[:30]))
        return

    if msg == Btn.LIST_USERS:
        users = db.get_all_users_for_admin()
        if not users:
            await update.message.reply_text("📭", reply_markup=user_mgmt_menu())
            return
        await update.message.reply_text(f"👥 ({len(users)})", parse_mode="Markdown",
                                        reply_markup=users_list_inline(users[:30]))
        return

    if msg == Btn.SEARCH_USER:
        ctx.user_data["state"] = "search_user"
        await update.message.reply_text("🔍 آیدی یا @یوزرنیم:\n/cancel", reply_markup=cancel_keyboard())
        return

    if msg == Btn.BAN_TOGGLE:
        ctx.user_data["state"] = "ban_user"
        await update.message.reply_text("🚫 آیدی:\n/cancel", reply_markup=cancel_keyboard())
        return

    if msg == Btn.EDIT_USER_COINS:
        ctx.user_data["state"] = "edit_user_coins"
        await update.message.reply_text("💎 `user_id coins`\n/cancel", parse_mode="Markdown",
                                        reply_markup=cancel_keyboard())
        return

    if msg == Btn.ADMINS:
        await update.message.reply_text("👑", reply_markup=admin_mgmt_menu())
        return

    if msg == Btn.ADD_ADMIN:
        ctx.user_data["state"] = "add_admin"
        await update.message.reply_text("👑 آیدی:\n/cancel", reply_markup=cancel_keyboard())
        return

    if msg == Btn.DEL_ADMIN:
        ctx.user_data["state"] = "remove_admin"
        await update.message.reply_text("🗑️ آیدی:\n/cancel", reply_markup=cancel_keyboard())
        return

    if msg == Btn.LIST_ADMINS:
        admins = db.get_admins()
        txt = "👑 **ادمین‌ها:**\n\n📌 **اصلی:**\n" + "\n".join(f"• `{a}`" for a in ADMIN_IDS)
        if admins:
            txt += "\n\n📌 **اضافه‌شده:**\n" + "\n".join(
                f"• `{a['user_id']}` @{a['username'] or '-'}" for a in admins)
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=admin_mgmt_menu())
        return

    if msg == Btn.TREASURY:
        await update.message.reply_text("🏛️ خزانه:", reply_markup=treasury_menu())
        return

    if msg == Btn.TREASURY_VIEW:
        await update.message.reply_text(f"🏛️ **موجودی:** **{db.get_treasury_balance()}** {COIN_NAME}",
                                        parse_mode="Markdown", reply_markup=treasury_menu())
        return

    if msg == Btn.TREASURY_WITHDRAW:
        bal = db.get_treasury_balance()
        if bal <= 0:
            await update.message.reply_text("📭 خالی!", reply_markup=treasury_menu())
            return
        ctx.user_data["state"] = "treasury_withdraw"
        await update.message.reply_text(f"📤 موجودی: **{bal}**\nمقدار:\n/cancel",
                                        parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if msg == Btn.TREASURY_HISTORY:
        history = db.get_treasury_history()
        if not history:
            await update.message.reply_text("📭", reply_markup=treasury_menu())
            return
        txt = "📜 **تاریخچه:**\n\n"
        for h in history[:15]:
            icon = "➕" if h["amount"] > 0 else "➖"
            txt += f"{icon} {abs(h['amount'])} | {h['description'] or '?'} | {h['created_at'][:16]}\n"
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=treasury_menu())
        return

    if msg == Btn.BROADCAST:
        ctx.user_data["state"] = "broadcast"
        await update.message.reply_text("📨 پیام:\n/cancel", reply_markup=cancel_keyboard())
        return

    if msg == Btn.IRAN_TIME:
        try:
            import jdatetime
            import pytz
            from datetime import datetime as dt
            iran_tz = pytz.timezone("Asia/Tehran")
            now_iran = dt.now(pytz.utc).astimezone(iran_tz)
            now_jalali = jdatetime.datetime.fromgregorian(datetime=now_iran)
            jalali_str = now_jalali.strftime("%Y/%m/%d %H:%M:%S")
            weekdays = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
            day_name = weekdays[now_jalali.weekday()]
            gregorian_str = now_iran.strftime("%Y-%m-%d %H:%M:%S")
            await update.message.reply_text(
                f"🕐 **ساعت ایران**\n\n"
                f"📅 شمسی: **{jalali_str}**\n"
                f"📅 میلادی: **{gregorian_str}**\n"
                f"📆 روز: **{day_name}**\n\n"
                f"💡 مهلت مسابقات با این زمان مقایسه می‌شود.",
                parse_mode="Markdown", reply_markup=admin_menu())
        except ImportError:
            await update.message.reply_text("❌ `pip install jdatetime pytz`",
                                            parse_mode="Markdown", reply_markup=admin_menu())
        return

    await update.message.reply_text(f"👑 💰 **{db.get_coins(uid)}** {COIN_NAME}",
                                    parse_mode="Markdown", reply_markup=admin_menu())


# ═══════════════════════════════════
#         USER NAVIGATION
# ═══════════════════════════════════
async def user_navigation(update, ctx, uid, msg):

    if msg == Btn.BACK_MAIN:
        ctx.user_data.clear()
        sn = db.get_special_name(uid)
        coins = db.get_coins(uid)
        await update.message.reply_text(f"👤 **{sn}** | 💰 **{coins}** {COIN_NAME}",
                                        parse_mode="Markdown", reply_markup=user_menu())
        return

    if msg == Btn.MATCHES:
        matches = db.get_upcoming_matches()
        if not matches:
            await update.message.reply_text("📭 مسابقه‌ای نیست.", reply_markup=user_menu())
            return
        await update.message.reply_text("⚽ **مسابقات پیش‌رو:**", parse_mode="Markdown",
                                        reply_markup=upcoming_matches_inline(matches))
        return

    if msg == Btn.MY_PREDS:
        await show_my_preds(update, uid)
        return

    if msg == Btn.HELP:
        await update.message.reply_text(
            "📋 **راهنما**\n\n1️⃣ ⚽ مسابقات → انتخاب\n2️⃣ 🎯 گزینه\n3️⃣ 💰 مبلغ\n4️⃣ ✅ تایید\n\n"
            f"📊 {int(HOUSE_FEE * 100)}٪ مالیات + {100 - int(HOUSE_FEE * 100)}٪ تقسیم تناسبی\n\n"
            f"🔄 تا قبل از مهلت می‌توانید شرط را لغو و تغییر دهید.",
            parse_mode="Markdown", reply_markup=user_menu())
        return

    if msg == Btn.ACCOUNT:
        sn = db.get_special_name(uid)
        coins = db.get_coins(uid)
        await update.message.reply_text(f"👤 **{sn}**\n💰 موجودی: **{coins}** {COIN_NAME}",
                                        parse_mode="Markdown", reply_markup=account_menu())
        return

    if msg == Btn.DEPOSIT:
        sn = db.get_special_name(uid)
        await update.message.reply_text(
            f"مبلغ مورد نظر برای افزایش موجودی را از طریق "
            f"ربات @Bslifebot به اسم خاص `{BSLIFE_OUR_NAME}` واریز نمایید.\n\n"
            f"فرمت واریز:\n"
            f"`gift {BSLIFE_OUR_NAME} 1000`\n\n"
            f"❗️قبل از انجام عملیات، اطمینان حاصل کنید "
            f"اسم خاص ثبت شده در @BSRiskBot و @Bslifebot یکسان باشد.❗️\n"
            f"👤 اسم خاص شما: **{sn}**\n\n"
            f"هرگونه اشتباه از این بابت به گردن خود شماست💯",
            parse_mode="Markdown", reply_markup=account_menu())
        return

    if msg == Btn.WITHDRAW:
        sn = db.get_special_name(uid)
        coins = db.get_coins(uid)
        if coins <= 0:
            await update.message.reply_text("❌ موجودی صفر!", reply_markup=account_menu())
            return
        if coins < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ حداقل برداشت **{MIN_WITHDRAW}** {COIN_NAME} است!\n"
                f"💰 موجودی شما: **{coins}** {COIN_NAME}",
                parse_mode="Markdown", reply_markup=account_menu())
            return

        await update.message.reply_text(
            f"❌ مطمئن شوید که آخرین بازدید اکانت بمب شما "
            f"درست باشد. در غیر این صورت مبلغ برداشت شده به شما "
            f"تعلق نخواهد گرفت و مسئولیت آن بر عهده ربات نمیباشد. ❌\n\n"
            f"❗️قبل از انجام عملیات، اطمینان حاصل کنید "
            f"اسم خاص ثبت شده در @BSRiskBot و @Bslifebot یکسان باشد.❗️\n"
            f"👤 اسم خاص شما: **{sn}**\n\n"
            f"هرگونه اشتباه از این بابت به گردن خود شماست💯",
            parse_mode="Markdown")

        ctx.user_data["state"] = "withdraw_amount"
        await update.message.reply_text(
            f"📤 **مقدار برداشت را وارد کنید:**\n"
            f"💰 موجودی: **{coins}** {COIN_NAME}\n"
            f"حداقل: {MIN_WITHDRAW}\n\n/cancel",
            parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if msg == Btn.EDIT_NAME:
        ctx.user_data["state"] = "edit_special_name"
        await update.message.reply_text(
            "✏️ **ویرایش اسم**\n\n• حروف انگلیسی | ۳ تا ۱۶\nمثال: `Mori`\n\n/cancel",
            parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    sn = db.get_special_name(uid)
    coins = db.get_coins(uid)
    await update.message.reply_text(f"👤 **{sn}** | 💰 **{coins}** {COIN_NAME}",
                                    parse_mode="Markdown", reply_markup=user_menu())


# ═══════════════════════════════════
#         PROCESS STATE
# ═══════════════════════════════════
async def process_state(update, ctx, state, msg, uid, admin):

    if state in ("set_special_name", "edit_special_name"):
        name = validate_special_name(msg)
        if not name:
            await update.message.reply_text("❌ نامعتبر!\n• حروف انگلیسی | ۳ تا ۱۶\n\nدوباره:",
                                            parse_mode="Markdown")
            return
        if db.is_special_name_taken(name, exclude_uid=uid):
            await update.message.reply_text(f"❌ **{name}** گرفته شده!", parse_mode="Markdown")
            return
        if db.set_special_name(uid, name):
            db.log_activity(uid, "special_name", name)
            ctx.user_data.clear()
            await update.message.reply_text(f"✅ اسم: **{name}** 🎉",
                                            parse_mode="Markdown", reply_markup=get_menu(uid))
        else:
            await update.message.reply_text("❌ خطا! دوباره:")
        return

    if state == "custom_bet":
        mid = ctx.user_data.get("bet_match")
        pred = ctx.user_data.get("bet_pred")
        if not mid or not pred:
            ctx.user_data.clear()
            await update.message.reply_text("❌ خطا!", reply_markup=user_menu())
            return
        try:
            amount = int(msg)
        except ValueError:
            await update.message.reply_text(f"❌ عدد! {MIN_BET}-{MAX_BET}")
            return
        if amount < MIN_BET or amount > MAX_BET:
            await update.message.reply_text(f"❌ {MIN_BET} تا {MAX_BET}!")
            return
        m = db.get_match(mid)
        if not m:
            ctx.user_data.clear()
            await update.message.reply_text("❌ مسابقه نیست.", reply_markup=user_menu())
            return
        option_text = m[pred]
        coins = db.get_coins(uid)
        ctx.user_data.clear()
        await update.message.reply_text(
            f"⚠️ **تایید**\n\n⚽ #{mid}\n🎯 {option_text}\n💰 {amount}\n💎 {coins}",
            parse_mode="Markdown", reply_markup=confirm_bet_inline(mid, pred, amount, option_text))
        return

    if state == "withdraw_amount":
        try:
            amount = int(msg)
        except ValueError:
            await update.message.reply_text("❌ عدد معتبر وارد کنید!\n/cancel")
            return
        if amount < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ حداقل برداشت **{MIN_WITHDRAW}** {COIN_NAME} است!",
                parse_mode="Markdown")
            return
        if amount <= 0:
            await update.message.reply_text("❌ مقدار باید مثبت باشد!")
            return
        coins = db.get_coins(uid)
        if amount > coins:
            await update.message.reply_text(
                f"❌ موجودی کافی نیست!\n💰 موجودی: {coins} {COIN_NAME}")
            return
        sn = db.get_special_name(uid)
        if not sn:
            ctx.user_data.clear()
            await update.message.reply_text("❌ اسم خاص ندارید!", reply_markup=user_menu())
            return
        result = db.remove_coins(uid, amount, f"برداشت: {amount}")
        if result == -1:
            await update.message.reply_text("❌ موجودی کافی نیست!")
            return
        req_id = db.create_withdraw_request(uid, sn, amount)
        db.log_activity(uid, "withdraw_request", f"req={req_id}, amount={amount}")
        ctx.user_data.clear()
        await update.message.reply_text(
            f"⏳ **درخواست #{req_id} ثبت شد!**\n\n"
            f"💰 **{amount}** {COIN_NAME}\n👤 **{sn}**\n\n⏱ صبر کنید...",
            parse_mode="Markdown", reply_markup=user_menu())
        return

    if state in ("inline_add_coins", "inline_sub_coins", "inline_set_coins"):
        tid = ctx.user_data.get("target_user")
        if not tid:
            ctx.user_data.clear()
            await update.message.reply_text("❌ خطا!", reply_markup=admin_menu())
            return
        try:
            amount = int(msg)
        except ValueError:
            await update.message.reply_text("❌ عدد!\n/cancel")
            return
        u = db.get_user(tid)
        if not u:
            ctx.user_data.clear()
            await update.message.reply_text("❌ کاربر نیست!", reply_markup=admin_menu())
            return
        old = u["coins"]
        sn = u["special_name"] or u["first_name"] or str(tid)
        if state == "inline_add_coins":
            if amount <= 0:
                await update.message.reply_text("❌ مثبت!")
                return
            db.set_coins(tid, old + amount)
            action = f"➕ {amount}"
        elif state == "inline_sub_coins":
            if amount <= 0:
                await update.message.reply_text("❌ مثبت!")
                return
            if amount > old:
                await update.message.reply_text(f"❌ موجودی: {old}")
                return
            db.set_coins(tid, old - amount)
            action = f"➖ {amount}"
        else:
            if amount < 0:
                await update.message.reply_text("❌ منفی!")
                return
            db.set_coins(tid, amount)
            action = f"= {amount}"
        new = db.get_coins(tid)
        db.log_activity(uid, "edit_coins", f"{tid}: {old}→{new}")
        ctx.user_data.clear()
        await update.message.reply_text(f"✅ **{action}**\n👤 **{sn}**\n💰 {old} → **{new}**",
                                        parse_mode="Markdown", reply_markup=admin_menu())
        return

    if state == "add_match_photo":
        if msg == "ندارد":
            ctx.user_data["match_photo"] = None
        else:
            await update.message.reply_text("🖼️ عکس یا `ندارد`", parse_mode="Markdown")
            return
        ctx.user_data["state"] = "add_match_caption"
        await update.message.reply_text("📝 **متن بازی:**\n/cancel", parse_mode="Markdown",
                                        reply_markup=cancel_keyboard())
        return

    if state == "add_match_caption":
        ctx.user_data["match_caption"] = msg
        ctx.user_data["state"] = "add_match_option1"
        await update.message.reply_text("🟠 **گزینه اول:**\nمثال: `تیم نارنجی میبره`\n/cancel",
                                        parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if state == "add_match_option1":
        ctx.user_data["match_option1"] = msg
        ctx.user_data["state"] = "add_match_option2"
        await update.message.reply_text("🤝 **گزینه دوم (مساوی):**\n/cancel",
                                        parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if state == "add_match_option2":
        ctx.user_data["match_option2"] = msg
        ctx.user_data["state"] = "add_match_option3"
        await update.message.reply_text("🟡 **گزینه سوم:**\n/cancel",
                                        parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if state == "add_match_option3":
        ctx.user_data["match_option3"] = msg
        ctx.user_data["state"] = "add_match_deadline"
        await update.message.reply_text("📅 **مهلت (ایران):**\nمثال: `۱۴۰۵/۰۴/۱۵ ۲۲:۳۰`\n/cancel",
                                        parse_mode="Markdown", reply_markup=cancel_keyboard())
        return

    if state == "add_match_deadline":
        mid = db.add_match(
            caption=ctx.user_data.get("match_caption", ""), deadline=msg,
            option_1=ctx.user_data.get("match_option1", "گزینه ۱"),
            option_2=ctx.user_data.get("match_option2", "مساوی"),
            option_3=ctx.user_data.get("match_option3", "گزینه ۳"),
            photo_id=ctx.user_data.get("match_photo"), created_by=uid)
        db.log_activity(uid, "add_match", f"#{mid}")
        ctx.user_data.clear()
        await update.message.reply_text(f"✅ مسابقه **#{mid}** اضافه شد! 🎉",
                                        parse_mode="Markdown", reply_markup=admin_menu())
        return

    if state == "add_channel":
        identifier = msg.strip()
        try:
            chat = await ctx.bot.get_chat(identifier)
            if db.add_channel(identifier, chat.title, added_by=uid):
                await update.message.reply_text(f"✅ {chat.title or identifier} اضافه شد.",
                                                reply_markup=channel_menu())
            else:
                await update.message.reply_text("❌ قبلاً ثبت شده!", reply_markup=channel_menu())
        except TelegramError:
            await update.message.reply_text("❌ ربات ادمین نیست!", reply_markup=channel_menu())
        ctx.user_data.clear()
        return

    if state == "remove_channel":
        chs = db.get_channels()
        if msg.isdigit():
            idx = int(msg) - 1
            if 0 <= idx < len(chs):
                db.remove_channel_by_id(chs[idx]["id"])
                await update.message.reply_text("✅ حذف شد.", reply_markup=channel_menu())
            else:
                await update.message.reply_text("❌ نامعتبر!", reply_markup=channel_menu())
        else:
            db.remove_channel_by_identifier(msg.strip())
            await update.message.reply_text("✅ حذف شد.", reply_markup=channel_menu())
        ctx.user_data.clear()
        return

    if state == "search_user":
        tid = None
        if msg.isdigit():
            tid = int(msg)
        elif msg.startswith("@"):
            r = db.find_user_by_username(msg[1:])
            if r:
                tid = r["user_id"]
        if tid:
            u = db.get_user(tid)
            if u:
                sn = u["special_name"] or "ندارد"
                ban = "🚫" if u["is_banned"] else "✅"
                await update.message.reply_text(
                    f"👤 `{u['user_id']}` @{u['username'] or '-'}\n✨ **{sn}**\n💰 {u['coins']}\n{ban}",
                    parse_mode="Markdown", reply_markup=user_mgmt_menu())
            else:
                await update.message.reply_text("❌ یافت نشد.", reply_markup=user_mgmt_menu())
        else:
            await update.message.reply_text("❌ نامعتبر.", reply_markup=user_mgmt_menu())
        ctx.user_data.clear()
        return

    if state == "edit_user_coins":
        try:
            p = msg.split()
            tid, new = int(p[0]), int(p[1])
        except (ValueError, IndexError):
            await update.message.reply_text("❌ `user_id coins`", parse_mode="Markdown")
            return
        u = db.get_user(tid)
        if not u:
            await update.message.reply_text("❌ نیست!", reply_markup=user_mgmt_menu())
            ctx.user_data.clear()
            return
        old = u["coins"]
        db.set_coins(tid, new)
        db.log_activity(uid, "edit_coins", f"{tid}: {old}->{new}")
        ctx.user_data.clear()
        await update.message.reply_text(f"✅ `{tid}` | {old} → **{new}**",
                                        parse_mode="Markdown", reply_markup=user_mgmt_menu())
        return

    if state == "ban_user":
        try:
            tid = int(msg)
        except ValueError:
            await update.message.reply_text("❌ آیدی عددی!")
            return
        u = db.get_user(tid)
        if not u:
            await update.message.reply_text("❌ نیست.", reply_markup=user_mgmt_menu())
            ctx.user_data.clear()
            return
        if u["is_banned"]:
            db.unban_user(tid)
            t = f"✅ `{tid}` آزاد"
        else:
            db.ban_user(tid)
            t = f"🚫 `{tid}` بن"
        db.log_activity(uid, "ban", str(tid))
        ctx.user_data.clear()
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=user_mgmt_menu())
        return

    if state == "add_admin":
        try:
            tid = int(msg)
            db.add_admin(tid, added_by=uid)
            db.log_activity(uid, "add_admin", str(tid))
            await update.message.reply_text(f"✅ `{tid}`", parse_mode="Markdown",
                                            reply_markup=admin_mgmt_menu())
        except ValueError:
            await update.message.reply_text("❌ آیدی!")
            return
        ctx.user_data.clear()
        return

    if state == "remove_admin":
        try:
            tid = int(msg)
            db.remove_admin(tid)
            db.log_activity(uid, "remove_admin", str(tid))
            await update.message.reply_text(f"✅ `{tid}` حذف", parse_mode="Markdown",
                                            reply_markup=admin_mgmt_menu())
        except ValueError:
            await update.message.reply_text("❌ آیدی!")
            return
        ctx.user_data.clear()
        return

    if state == "treasury_withdraw":
        try:
            amount = int(msg)
        except ValueError:
            await update.message.reply_text("❌ عدد!")
            return
        if amount <= 0:
            await update.message.reply_text("❌ مثبت!")
            return
        if db.withdraw_treasury(amount, f"ادمین {uid}"):
            db.log_activity(uid, "treasury_withdraw", str(amount))
            ctx.user_data.clear()
            await update.message.reply_text(
                f"✅ **{amount}** برداشت.\n🏛️ باقی: **{db.get_treasury_balance()}**",
                parse_mode="Markdown", reply_markup=treasury_menu())
        else:
            await update.message.reply_text(f"❌ کافی نیست! ({db.get_treasury_balance()})",
                                            reply_markup=treasury_menu())
        return

    if state == "broadcast":
        users = db.get_all_active_user_ids()
        total = len(users)
        sent = failed = 0
        await update.message.reply_text(f"📨 ارسال به {total}...")
        for i, u in enumerate(users):
            try:
                await ctx.bot.send_message(u["user_id"], msg, parse_mode="Markdown")
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(BROADCAST_DELAY)
            if (i + 1) % 50 == 0:
                await update.message.reply_text(f"⏳ {i + 1}/{total}...")
        db.log_activity(uid, "broadcast", f"{sent}/{failed}")
        ctx.user_data.clear()
        await update.message.reply_text(f"✅ {sent} | ❌ {failed}", reply_markup=admin_menu())
        return


# ═══════════════════════════════════
#          DISPLAY HELPERS
# ═══════════════════════════════════
async def show_my_preds(update, uid):
    preds = db.get_user_predictions(uid)
    if not preds:
        await update.message.reply_text("📭 پیش‌بینی‌ای نیست.", reply_markup=user_menu())
        return
    status_map = {"pending": "⏳", "won": "✅", "lost": "❌"}
    txt = "📊 **پیش‌بینی‌ها:**\n\n"
    for p in preds[:10]:
        opt_key = p["prediction"]
        opt_text = p[opt_key] if opt_key in ("option_1", "option_2", "option_3") else opt_key
        payout = f" 🎉+{p['payout']}" if p["payout"] else ""
        txt += f"⚽ #{p['match_id']} | {opt_text} | 💰{p['coins_bet']} | {status_map.get(p['status'], '?')}{payout}\n"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=user_menu())


# ═══════════════════════════════════
#          AUTO CLOSE
# ═══════════════════════════════════
async def auto_close_matches(ctx):
    try:
        closed = db.close_expired_matches()
        if closed > 0:
            logger.info(f"⏰ Auto-closed {closed} match(es)")
    except Exception as e:
        logger.error(f"Auto-close error: {e}")


# ═══════════════════════════════════
#              MAIN
# ═══════════════════════════════════
def main():
    builder = Application.builder().token(BOT_TOKEN)
    proxy = PROXY_URL or PROXY_SOCKS5_URL
    if proxy:
        logger.info(f"🔌 Proxy: {proxy}")
        builder = builder.proxy(proxy).get_updates_proxy(proxy)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))

    app.job_queue.run_repeating(auto_close_matches, interval=30, first=5)

    logger.info("🤖 Bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()