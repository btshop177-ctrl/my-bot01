import sqlite3
import logging
import threading
import jdatetime
import pytz
from datetime import datetime
from config import DATABASE_PATH, COIN_NAME, HOUSE_FEE

logger = logging.getLogger(__name__)

IRAN_TZ = pytz.timezone("Asia/Tehran")


def iran_now():
    return jdatetime.datetime.now(tz=IRAN_TZ)


class Database:
    def __init__(self, path=DATABASE_PATH):
        self.path = path
        self._local = threading.local()
        self._create_tables()

    def _get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    @property
    def conn(self):
        return self._get_conn()

    def _create_tables(self):
        c = self.conn
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT,
            special_name TEXT UNIQUE COLLATE NOCASE, coins INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0, total_lost INTEGER DEFAULT 0,
            total_bets INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, photo_id TEXT DEFAULT NULL,
            caption TEXT NOT NULL, option_1 TEXT NOT NULL DEFAULT 'تیم اول',
            option_2 TEXT NOT NULL DEFAULT 'مساوی', option_3 TEXT NOT NULL DEFAULT 'تیم دوم',
            deadline TEXT NOT NULL, status TEXT DEFAULT 'upcoming',
            result TEXT DEFAULT NULL, created_by INTEGER DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP, settled INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL, prediction TEXT NOT NULL,
            coins_bet INTEGER NOT NULL, status TEXT DEFAULT 'pending',
            payout INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS mandatory_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT, channel_identifier TEXT NOT NULL,
            channel_title TEXT, is_active INTEGER DEFAULT 1,
            added_by INTEGER DEFAULT NULL, added_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS treasury (
            id INTEGER PRIMARY KEY AUTOINCREMENT, amount INTEGER NOT NULL,
            match_id INTEGER, description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY, username TEXT,
            level TEXT DEFAULT 'admin', added_by INTEGER DEFAULT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            action TEXT NOT NULL, details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            special_name TEXT NOT NULL, amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending', result TEXT DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME DEFAULT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS deposit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            special_name TEXT NOT NULL, amount INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pred_user ON predictions(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pred_match ON predictions(match_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_match_status ON matches(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_special ON users(special_name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_withdraw_status ON withdraw_requests(status)")
        c.commit()

    # ═══════════ USER ═══════════
    def get_user(self, uid):
        return self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

    def create_user(self, uid, username=None, fn=None, ln=None):
        if self.get_user(uid): return False
        self.conn.execute("INSERT INTO users(user_id,username,first_name,last_name) VALUES(?,?,?,?)",
                          (uid, username, fn, ln))
        self.conn.commit(); return True

    def update_user_info(self, uid, username=None, fn=None, ln=None):
        parts, params = [], []
        if username is not None: parts.append("username=?"); params.append(username)
        if fn is not None: parts.append("first_name=?"); params.append(fn)
        if ln is not None: parts.append("last_name=?"); params.append(ln)
        if parts:
            params.append(uid)
            self.conn.execute(f"UPDATE users SET {','.join(parts)} WHERE user_id=?", params)
            self.conn.commit()

    def ensure_user(self, uid, username=None, fn=None, ln=None):
        if not self.get_user(uid): self.create_user(uid, username, fn, ln)
        else: self.update_user_info(uid, username, fn, ln)

    def get_coins(self, uid):
        r = self.conn.execute("SELECT coins FROM users WHERE user_id=?", (uid,)).fetchone()
        return r["coins"] if r else 0

    def set_coins(self, uid, amount):
        self.conn.execute("UPDATE users SET coins=? WHERE user_id=?", (amount, uid))
        self.conn.commit()

    def add_coins(self, uid, amount, desc=""):
        with self.conn:
            self.conn.execute("UPDATE users SET coins=coins+? WHERE user_id=?", (amount, uid))
        return self.get_coins(uid)

    def remove_coins(self, uid, amount, desc=""):
        with self.conn:
            r = self.conn.execute("UPDATE users SET coins=coins-? WHERE user_id=? AND coins>=?",
                                  (amount, uid, amount))
            if r.rowcount == 0: return -1
        return self.get_coins(uid)

    def get_special_name(self, uid):
        r = self.conn.execute("SELECT special_name FROM users WHERE user_id=?", (uid,)).fetchone()
        return r["special_name"] if r else None

    def set_special_name(self, uid, name):
        try:
            self.conn.execute("UPDATE users SET special_name=? WHERE user_id=?", (name, uid))
            self.conn.commit(); return True
        except sqlite3.IntegrityError: return False

    def has_special_name(self, uid):
        return self.get_special_name(uid) is not None

    def is_special_name_taken(self, name, exclude_uid=None):
        if exclude_uid:
            r = self.conn.execute("SELECT user_id FROM users WHERE special_name=? COLLATE NOCASE AND user_id!=?",
                                  (name, exclude_uid)).fetchone()
        else:
            r = self.conn.execute("SELECT user_id FROM users WHERE special_name=? COLLATE NOCASE",
                                  (name,)).fetchone()
        return r is not None

    def find_user_by_special_name(self, name):
        return self.conn.execute("SELECT * FROM users WHERE special_name=? COLLATE NOCASE", (name,)).fetchone()

    def find_user_by_username(self, username):
        return self.conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()

    def ban_user(self, uid):
        self.conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,)); self.conn.commit()

    def unban_user(self, uid):
        self.conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,)); self.conn.commit()

    def is_banned(self, uid):
        r = self.conn.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,)).fetchone()
        return r is not None and r["is_banned"] == 1

    def get_all_users(self):
        return self.conn.execute("SELECT * FROM users WHERE special_name IS NOT NULL ORDER BY coins DESC").fetchall()

    def get_all_users_for_admin(self):
        return self.conn.execute(
            "SELECT user_id,username,first_name,last_name,special_name,coins,total_bets,total_won,total_lost,is_banned "
            "FROM users ORDER BY CASE WHEN special_name IS NOT NULL THEN 0 ELSE 1 END, coins DESC").fetchall()

    def get_all_active_user_ids(self):
        return self.conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()

    # ═══════════ MATCH ═══════════
    def add_match(self, caption, deadline, option_1, option_2, option_3, photo_id=None, created_by=None):
        cur = self.conn.execute(
            "INSERT INTO matches(caption,deadline,option_1,option_2,option_3,photo_id,created_by) VALUES(?,?,?,?,?,?,?)",
            (caption, deadline, option_1, option_2, option_3, photo_id, created_by))
        self.conn.commit(); return cur.lastrowid

    def get_match(self, mid):
        return self.conn.execute("SELECT * FROM matches WHERE id=?", (mid,)).fetchone()

    def get_upcoming_matches(self, limit=10):
        return self.conn.execute(
            "SELECT * FROM matches WHERE status='upcoming' ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def get_all_matches(self, limit=15):
        return self.conn.execute("SELECT * FROM matches ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def close_match(self, mid):
        self.conn.execute("UPDATE matches SET status='closed' WHERE id=? AND status='upcoming'", (mid,))
        self.conn.commit()

    def reopen_match(self, mid):
        self.conn.execute("UPDATE matches SET status='upcoming' WHERE id=? AND status='closed'", (mid,))
        self.conn.commit()

    def set_match_result(self, mid, result):
        self.conn.execute("UPDATE matches SET result=?,status='finished' WHERE id=? AND status IN ('upcoming','closed')",
                          (result, mid))
        self.conn.commit()

    def _parse_deadline(self, deadline_str):
        """تبدیل مهلت به jdatetime با timezone ایران"""
        deadline = deadline_str.strip()
        for fa, en in zip("۰۱۲۳۴۵۶۷۸۹", "0123456789"):
            deadline = deadline.replace(fa, en)
        dt = jdatetime.datetime.strptime(deadline, "%Y/%m/%d %H:%M")
        return dt.replace(tzinfo=IRAN_TZ)

    def close_expired_matches(self):
        try:
            now = iran_now()
            upcoming = self.get_upcoming_matches(limit=100)
            closed = 0
            for m in upcoming:
                try:
                    deadline_dt = self._parse_deadline(m["deadline"])
                    if now >= deadline_dt:
                        self.conn.execute(
                            "UPDATE matches SET status='closed' WHERE id=? AND status='upcoming'",
                            (m["id"],))
                        closed += 1
                        logger.info(f"⏰ Match #{m['id']} auto-closed")
                except Exception:
                    continue
            if closed > 0: self.conn.commit()
            return closed
        except Exception as e:
            logger.warning(f"auto-close error: {e}")
            return 0

    # ═══════════ PREDICTION ═══════════
    def place_prediction(self, uid, mid, pred, coins_bet):
        m = self.get_match(mid)
        if not m: return (False, "❌ مسابقه یافت نشد!", None)
        if m["status"] != "upcoming":
            return (False, "❌ مهلت پیش‌بینی تمام شده!", None)
        try:
            now = iran_now()
            deadline_dt = self._parse_deadline(m["deadline"])
            if now >= deadline_dt:
                self.conn.execute("UPDATE matches SET status='closed' WHERE id=? AND status='upcoming'", (mid,))
                self.conn.commit()
                return (False, "❌ مهلت پیش‌بینی تمام شده!", None)
        except Exception:
            pass
        try:
            with self.conn:
                ex = self.conn.execute("SELECT id FROM predictions WHERE user_id=? AND match_id=?",
                                       (uid, mid)).fetchone()
                if ex: return (False, "❌ قبلاً پیش‌بینی کرده‌اید!", None)
                r = self.conn.execute(
                    "UPDATE users SET coins=coins-?,total_bets=total_bets+1 WHERE user_id=? AND coins>=?",
                    (coins_bet, uid, coins_bet))
                if r.rowcount == 0:
                    c = self.get_coins(uid)
                    return (False, f"❌ موجودی کافی نیست!\n💰 موجودی: {c} {COIN_NAME}", None)
                cur = self.conn.execute(
                    "INSERT INTO predictions(user_id,match_id,prediction,coins_bet) VALUES(?,?,?,?)",
                    (uid, mid, pred, coins_bet))
            option_map = {"option_1": m["option_1"], "option_2": m["option_2"], "option_3": m["option_3"]}
            bal = self.get_coins(uid)
            msg = (f"✅ **پیش‌بینی ثبت شد!**\n\n⚽ مسابقه: #{mid}\n"
                   f"🎯 انتخاب: {option_map.get(pred, pred)}\n💰 شرط: {coins_bet} {COIN_NAME}\n💎 موجودی: {bal} {COIN_NAME}")
            return (True, msg, cur.lastrowid)
        except Exception as e:
            logger.error(f"place_prediction error: {e}")
            return (False, "❌ خطای سیستمی!", None)

    def cancel_prediction(self, uid, mid):
        m = self.get_match(mid)
        if not m or m["status"] != "upcoming":
            return (False, "❌ مهلت تغییر شرط تمام شده!")
        try:
            now = iran_now()
            deadline_dt = self._parse_deadline(m["deadline"])
            if now >= deadline_dt:
                return (False, "❌ مهلت تغییر شرط تمام شده!")
        except Exception:
            pass
        pred = self.conn.execute(
            "SELECT * FROM predictions WHERE user_id=? AND match_id=? AND status='pending'",
            (uid, mid)).fetchone()
        if not pred:
            return (False, "❌ پیش‌بینی‌ای ندارید!")
        coins_bet = pred["coins_bet"]
        option_map = {"option_1": m["option_1"], "option_2": m["option_2"], "option_3": m["option_3"]}
        old_option = option_map.get(pred["prediction"], pred["prediction"])
        try:
            with self.conn:
                self.conn.execute("DELETE FROM predictions WHERE id=?", (pred["id"],))
                self.conn.execute("UPDATE users SET coins=coins+?, total_bets=total_bets-1 WHERE user_id=?",
                                  (coins_bet, uid))
            new_balance = self.get_coins(uid)
            return (True,
                f"✅ **شرط لغو شد!**\n\n⚽ مسابقه: #{mid}\n"
                f"🎯 قبلی: {old_option}\n💰 برگشت: +{coins_bet} {COIN_NAME}\n💎 موجودی: {new_balance} {COIN_NAME}")
        except Exception as e:
            logger.error(f"cancel_prediction error: {e}")
            return (False, "❌ خطای سیستمی!")

    def get_user_prediction_for_match(self, uid, mid):
        return self.conn.execute(
            "SELECT * FROM predictions WHERE user_id=? AND match_id=? AND status='pending'",
            (uid, mid)).fetchone()

    def get_user_predictions(self, uid, limit=20):
        return self.conn.execute(
            "SELECT p.*,m.caption,m.option_1,m.option_2,m.option_3,m.status as match_status,m.result,m.deadline "
            "FROM predictions p JOIN matches m ON p.match_id=m.id WHERE p.user_id=? ORDER BY p.created_at DESC LIMIT ?",
            (uid, limit)).fetchall()

    def get_match_predictions(self, mid):
        return self.conn.execute(
            "SELECT p.*,u.username,u.first_name,u.special_name "
            "FROM predictions p JOIN users u ON p.user_id=u.user_id WHERE p.match_id=?", (mid,)).fetchall()

    def settle_match(self, mid):
        m = self.get_match(mid)
        if not m or m["status"] != "finished" or not m["result"]:
            return (False, "❌ مسابقه نتیجه‌گذاری نشده.")
        if m["settled"]:
            return (False, "❌ قبلاً تسویه شده.")
        preds = self.get_match_predictions(mid)
        if not preds:
            self.conn.execute("UPDATE matches SET settled=1 WHERE id=?", (mid,))
            self.conn.commit()
            return (True, "🏁 هیچ پیش‌بینی‌ای ثبت نشده بود.")
        winners = [p for p in preds if p["prediction"] == m["result"] and p["status"] == "pending"]
        losers = [p for p in preds if p["prediction"] != m["result"] and p["status"] == "pending"]
        total_loser_coins = sum(p["coins_bet"] for p in losers)
        total_winner_bets = sum(p["coins_bet"] for p in winners)
        try:
            with self.conn:
                if len(winners) == 0 and len(losers) > 0:
                    for p in losers:
                        self.conn.execute("UPDATE predictions SET status='lost',payout=0 WHERE id=?", (p["id"],))
                        self.conn.execute("UPDATE users SET total_lost=total_lost+? WHERE user_id=?",
                                          (p["coins_bet"], p["user_id"]))
                    if total_loser_coins > 0:
                        self.conn.execute("INSERT INTO treasury(amount,match_id,description) VALUES(?,?,?)",
                                          (total_loser_coins, mid, f"همه باختن #{mid}"))
                    self.conn.execute("UPDATE matches SET settled=1 WHERE id=?", (mid,))
                    return (True, f"🏁 **تسویه #{mid}**\n\n❌ همه باختند! ({len(losers)} نفر)\n"
                                  f"🏛️ خزانه: +{total_loser_coins} {COIN_NAME}")
                elif len(losers) == 0 and len(winners) > 0:
                    for p in winners:
                        payout = p["coins_bet"]
                        self.conn.execute("UPDATE predictions SET status='won',payout=? WHERE id=?", (payout, p["id"]))
                        self.conn.execute("UPDATE users SET coins=coins+? WHERE user_id=?", (payout, p["user_id"]))
                    self.conn.execute("UPDATE matches SET settled=1 WHERE id=?", (mid,))
                    return (True, f"🏁 **تسویه #{mid}**\n\n✅ همه بردند! ({len(winners)} نفر)\n"
                                  f"💰 اصل شرط برگشت.\n🏛️ خزانه: +0")
                else:
                    house_cut = int(total_loser_coins * HOUSE_FEE)
                    prize_pool = total_loser_coins - house_cut
                    for p in losers:
                        self.conn.execute("UPDATE predictions SET status='lost',payout=0 WHERE id=?", (p["id"],))
                        self.conn.execute("UPDATE users SET total_lost=total_lost+? WHERE user_id=?",
                                          (p["coins_bet"], p["user_id"]))
                    total_paid = 0
                    for p in winners:
                        share = int(prize_pool * (p["coins_bet"] / total_winner_bets)) if total_winner_bets > 0 else 0
                        payout = p["coins_bet"] + share
                        self.conn.execute("UPDATE predictions SET status='won',payout=? WHERE id=?", (payout, p["id"]))
                        self.conn.execute("UPDATE users SET coins=coins+?,total_won=total_won+? WHERE user_id=?",
                                          (payout, share, p["user_id"]))
                        total_paid += payout
                    if house_cut > 0:
                        self.conn.execute("INSERT INTO treasury(amount,match_id,description) VALUES(?,?,?)",
                                          (house_cut, mid, f"مالیات #{mid}"))
                    self.conn.execute("UPDATE matches SET settled=1 WHERE id=?", (mid,))
                    return (True, f"🏁 **تسویه #{mid}**\n\n✅ برندگان: {len(winners)}\n"
                                  f"❌ بازندگان: {len(losers)}\n💰 جوایز: {total_paid} {COIN_NAME}\n"
                                  f"🏛️ خزانه: +{house_cut} {COIN_NAME}")
        except Exception as e:
            logger.error(f"settle error: {e}")
            return (False, f"❌ خطا: {e}")

    # ═══════════ TREASURY ═══════════
    def get_treasury_balance(self):
        r = self.conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM treasury").fetchone()
        return r["total"]

    def get_treasury_history(self, limit=20):
        return self.conn.execute("SELECT * FROM treasury ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def withdraw_treasury(self, amount, description="برداشت ادمین"):
        if amount > self.get_treasury_balance() or amount <= 0: return False
        self.conn.execute("INSERT INTO treasury(amount,description) VALUES(?,?)", (-amount, description))
        self.conn.commit(); return True

    # ═══════════ CHANNELS ═══════════
    def add_channel(self, identifier, title=None, added_by=None):
        if self.conn.execute("SELECT id FROM mandatory_channels WHERE channel_identifier=?",
                             (identifier,)).fetchone(): return False
        self.conn.execute("INSERT INTO mandatory_channels(channel_identifier,channel_title,added_by) VALUES(?,?,?)",
                          (identifier, title, added_by))
        self.conn.commit(); return True

    def remove_channel_by_id(self, row_id):
        self.conn.execute("DELETE FROM mandatory_channels WHERE id=?", (row_id,)); self.conn.commit()

    def remove_channel_by_identifier(self, identifier):
        self.conn.execute("DELETE FROM mandatory_channels WHERE channel_identifier=?", (identifier,)); self.conn.commit()

    def get_channels(self):
        return self.conn.execute("SELECT * FROM mandatory_channels WHERE is_active=1").fetchall()

    # ═══════════ ADMIN ═══════════
    def add_admin(self, uid, username=None, level="admin", added_by=None):
        self.conn.execute("INSERT OR REPLACE INTO admins(user_id,username,level,added_by) VALUES(?,?,?,?)",
                          (uid, username, level, added_by))
        self.conn.commit()

    def remove_admin(self, uid):
        self.conn.execute("DELETE FROM admins WHERE user_id=?", (uid,)); self.conn.commit()

    def get_admins(self):
        return self.conn.execute("SELECT * FROM admins").fetchall()

    def is_admin(self, uid):
        return self.conn.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone() is not None

    # ═══════════ WITHDRAW ═══════════
    def create_withdraw_request(self, uid, special_name, amount):
        cur = self.conn.execute("INSERT INTO withdraw_requests(user_id,special_name,amount) VALUES(?,?,?)",
                                (uid, special_name, amount))
        self.conn.commit(); return cur.lastrowid

    def get_pending_withdraws(self):
        return self.conn.execute(
            "SELECT * FROM withdraw_requests WHERE status='pending' ORDER BY created_at ASC").fetchall()

    def update_withdraw_status(self, req_id, status, result=None):
        self.conn.execute("UPDATE withdraw_requests SET status=?,result=?,processed_at=CURRENT_TIMESTAMP WHERE id=?",
                          (status, result, req_id))
        self.conn.commit()

    def log_deposit(self, uid, special_name, amount):
        self.conn.execute("INSERT INTO deposit_log(user_id,special_name,amount) VALUES(?,?,?)",
                          (uid, special_name, amount))
        self.conn.commit()

    # ═══════════ STATS ═══════════
    def get_stats(self):
        return {
            "total_users": self.conn.execute("SELECT COUNT(*) as c FROM users WHERE special_name IS NOT NULL").fetchone()["c"],
            "total_predictions": self.conn.execute("SELECT COUNT(*) as c FROM predictions").fetchone()["c"],
            "total_coins": self.conn.execute("SELECT COALESCE(SUM(coins),0) as c FROM users").fetchone()["c"],
            "active_matches": self.conn.execute("SELECT COUNT(*) as c FROM matches WHERE status='upcoming'").fetchone()["c"],
            "treasury": self.get_treasury_balance(),
        }

    def get_leaderboard(self, limit=10):
        return self.conn.execute(
            "SELECT user_id,username,first_name,special_name,coins,total_won,total_bets "
            "FROM users WHERE is_banned=0 AND special_name IS NOT NULL ORDER BY coins DESC LIMIT ?",
            (limit,)).fetchall()

    def log_activity(self, uid, action, details=""):
        self.conn.execute("INSERT INTO activity_log(user_id,action,details) VALUES(?,?,?)", (uid, action, details))
        self.conn.commit()

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close(); self._local.conn = None