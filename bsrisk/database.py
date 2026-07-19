from typing import Optional

import aiosqlite

from config import DB_PATH


class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self.db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.create_tables()

    async def close(self):
        if self.db:
            await self.db.close()
            self.db = None

    async def _ensure_column(self, table: str, column: str, definition: str):
        """افزودن ستون‌های نسخه‌های جدید بدون خراب کردن دیتابیس قبلی."""
        cursor = await self.db.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in await cursor.fetchall()}
        if column not in columns:
            await self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def create_tables(self):
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                game_name TEXT DEFAULT NULL,
                balance REAL DEFAULT 0.0,
                is_banned INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE NOT NULL,
                channel_title TEXT,
                channel_username TEXT,
                invite_link TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                group_title TEXT,
                owner_id INTEGER,
                forced_join_enabled INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # کانال‌های جوین اجباری هر گروه جدا از کانال‌های جوین اجباری PV هستند.
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS group_channels (
                group_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                channel_title TEXT,
                channel_username TEXT,
                invite_link TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, channel_id)
            )
        """)
        # هر مجوز یک رکورد مستقل دارد تا مالک بتواند بن و جوین اجباری را جداگانه واگذار کند.
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS group_admin_permissions (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission TEXT NOT NULL,
                granted_by INTEGER,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, user_id, permission)
            )
        """)

        # مهاجرت دیتابیس‌های قدیمی که جدول groups آنها فقط دو ستون داشت.
        await self._ensure_column("groups", "owner_id", "INTEGER")
        await self._ensure_column("groups", "forced_join_enabled", "INTEGER DEFAULT 0")
        await self.db.commit()

    # ═══════════════ کاربران ═══════════════
    async def add_user(self, user_id: int, username: str, full_name: str):
        await self.db.execute(
            """INSERT OR IGNORE INTO users (user_id, username, full_name)
               VALUES (?, ?, ?)""",
            (user_id, username, full_name)
        )
        await self.db.commit()

    async def update_user_info(self, user_id: int, username: str, full_name: str):
        await self.db.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
            (username, full_name, user_id)
        )
        await self.db.commit()

    async def set_game_name(self, user_id: int, game_name: str):
        await self.db.execute(
            "UPDATE users SET game_name = ? WHERE user_id = ?",
            (game_name, user_id)
        )
        await self.db.commit()

    async def get_game_name_exists(self, game_name: str, exclude_user_id: int = None) -> bool:
        if exclude_user_id:
            cursor = await self.db.execute(
                "SELECT user_id FROM users WHERE LOWER(game_name) = LOWER(?) AND user_id != ?",
                (game_name, exclude_user_id)
            )
        else:
            cursor = await self.db.execute(
                "SELECT user_id FROM users WHERE LOWER(game_name) = LOWER(?)",
                (game_name,)
            )
        return await cursor.fetchone() is not None

    async def get_user(self, user_id: int):
        cursor = await self.db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

    async def get_user_by_game_name(self, game_name: str):
        cursor = await self.db.execute(
            "SELECT * FROM users WHERE LOWER(game_name) = LOWER(?)", (game_name,)
        )
        return await cursor.fetchone()

    async def get_all_users(self):
        cursor = await self.db.execute("SELECT * FROM users")
        return await cursor.fetchall()

    async def get_user_count(self):
        cursor = await self.db.execute("SELECT COUNT(*) as count FROM users")
        row = await cursor.fetchone()
        return row[0]

    async def set_balance(self, user_id: int, amount: float):
        await self.db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
        await self.db.commit()

    async def add_balance(self, user_id: int, amount: float):
        await self.db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id)
        )
        await self.db.commit()

    async def set_banned(self, user_id: int, banned: bool):
        await self.db.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if banned else 0, user_id)
        )
        await self.db.commit()

    # ═══════════════ کانال‌های جوین اجباری سراسری (PV) ═══════════════
    async def add_channel(self, channel_id: str, title: str,
                          username: str, invite_link: str, added_by: int):
        await self.db.execute(
            """INSERT OR REPLACE INTO channels
               (channel_id, channel_title, channel_username, invite_link, added_by)
               VALUES (?, ?, ?, ?, ?)""",
            (channel_id, title, username, invite_link, added_by)
        )
        await self.db.commit()

    async def remove_channel(self, channel_id: str):
        await self.db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        await self.db.commit()

    async def get_all_channels(self):
        cursor = await self.db.execute("SELECT * FROM channels")
        return await cursor.fetchall()

    async def get_channel(self, channel_id: str):
        cursor = await self.db.execute(
            "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
        )
        return await cursor.fetchone()

    # ═══════════════ گروه‌ها ═══════════════
    async def add_group(self, group_id: int, title: str, owner_id: int = None):
        await self.db.execute(
            """INSERT INTO groups (group_id, group_title, owner_id)
               VALUES (?, ?, ?)
               ON CONFLICT(group_id) DO UPDATE SET
                 group_title = excluded.group_title,
                 owner_id = COALESCE(excluded.owner_id, groups.owner_id)""",
            (group_id, title, owner_id)
        )
        await self.db.commit()

    async def get_group(self, group_id: int):
        cursor = await self.db.execute("SELECT * FROM groups WHERE group_id = ?", (group_id,))
        return await cursor.fetchone()

    async def get_all_groups(self):
        cursor = await self.db.execute("SELECT * FROM groups")
        return await cursor.fetchall()

    async def set_group_forced_join(self, group_id: int, enabled: bool):
        await self.db.execute(
            "UPDATE groups SET forced_join_enabled = ? WHERE group_id = ?",
            (1 if enabled else 0, group_id)
        )
        await self.db.commit()

    async def get_group_channels(self, group_id: int):
        cursor = await self.db.execute(
            "SELECT * FROM group_channels WHERE group_id = ? ORDER BY added_at",
            (group_id,)
        )
        return await cursor.fetchall()

    async def get_group_channel(self, group_id: int, channel_id: str):
        cursor = await self.db.execute(
            "SELECT * FROM group_channels WHERE group_id = ? AND channel_id = ?",
            (group_id, channel_id)
        )
        return await cursor.fetchone()

    async def add_group_channel(self, group_id: int, channel_id: str, title: str,
                                username: str, invite_link: str, added_by: int):
        await self.db.execute(
            """INSERT OR REPLACE INTO group_channels
               (group_id, channel_id, channel_title, channel_username, invite_link, added_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (group_id, channel_id, title, username, invite_link, added_by)
        )
        await self.db.commit()

    async def remove_group_channel(self, group_id: int, channel_id: str):
        await self.db.execute(
            "DELETE FROM group_channels WHERE group_id = ? AND channel_id = ?",
            (group_id, channel_id)
        )
        await self.db.commit()

    # ═══════════════ مجوزهای مدیران گروه ═══════════════
    async def set_group_permission(self, group_id: int, user_id: int,
                                   permission: str, granted_by: int):
        await self.db.execute(
            """INSERT OR REPLACE INTO group_admin_permissions
               (group_id, user_id, permission, granted_by)
               VALUES (?, ?, ?, ?)""",
            (group_id, user_id, permission, granted_by)
        )
        await self.db.commit()

    async def remove_group_permission(self, group_id: int, user_id: int, permission: str):
        await self.db.execute(
            """DELETE FROM group_admin_permissions
               WHERE group_id = ? AND user_id = ? AND permission = ?""",
            (group_id, user_id, permission)
        )
        await self.db.commit()

    async def has_group_permission(self, group_id: int, user_id: int, permission: str) -> bool:
        cursor = await self.db.execute(
            """SELECT 1 FROM group_admin_permissions
               WHERE group_id = ? AND user_id = ? AND permission = ?""",
            (group_id, user_id, permission)
        )
        return await cursor.fetchone() is not None

    async def get_group_permissions(self, group_id: int):
        cursor = await self.db.execute(
            """SELECT * FROM group_admin_permissions
               WHERE group_id = ? ORDER BY user_id, permission""",
            (group_id,)
        )
        return await cursor.fetchall()


# یک نمونه مشترک برای تمام هندلرها و میدلورها
db = Database()
