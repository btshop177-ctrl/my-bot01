import aiosqlite
from config import DB_PATH
from typing import Optional


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
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.commit()

    # ═══════════════ کاربران ═══════════════

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def add_user(self, user_id: int, username: str, full_name: str):
        await self.db.execute(
            """INSERT OR IGNORE INTO users (user_id, username, full_name)
               VALUES (?, ?, ?)""",
            (user_id, username, full_name)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def update_user_info(self, user_id: int, username: str, full_name: str):
        await self.db.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
            (username, full_name, user_id)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def set_game_name(self, user_id: int, game_name: str):
        await self.db.execute(
            "UPDATE users SET game_name = ? WHERE user_id = ?",
            (game_name, user_id)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
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

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def get_user(self, user_id: int):
        cursor = await self.db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        return await cursor.fetchone()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def get_user_by_game_name(self, game_name: str):
        cursor = await self.db.execute(
            "SELECT * FROM users WHERE LOWER(game_name) = LOWER(?)",
            (game_name,)
        )
        return await cursor.fetchone()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def get_all_users(self):
        cursor = await self.db.execute("SELECT * FROM users")
        return await cursor.fetchall()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def get_user_count(self):
        cursor = await self.db.execute("SELECT COUNT(*) as count FROM users")
        row = await cursor.fetchone()
        return row[0]

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def set_balance(self, user_id: int, amount: float):
        await self.db.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (amount, user_id)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def add_balance(self, user_id: int, amount: float):
        await self.db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def set_banned(self, user_id: int, banned: bool):
        await self.db.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if banned else 0, user_id)
        )
        await self.db.commit()

    # ═══════════════ کانال‌ها ═══════════════

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def add_channel(self, channel_id: str, title: str,
                          username: str, invite_link: str, added_by: int):
        await self.db.execute(
            """INSERT OR REPLACE INTO channels
               (channel_id, channel_title, channel_username, invite_link, added_by)
               VALUES (?, ?, ?, ?, ?)""",
            (channel_id, title, username, invite_link, added_by)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def remove_channel(self, channel_id: str):
        await self.db.execute(
            "DELETE FROM channels WHERE channel_id = ?", (channel_id,)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def get_all_channels(self):
        cursor = await self.db.execute("SELECT * FROM channels")
        return await cursor.fetchall()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def get_channel(self, channel_id: str):
        cursor = await self.db.execute(
            "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
        )
        return await cursor.fetchone()

    # ═══════════════ گروه‌ها ═══════════════

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def add_group(self, group_id: int, title: str):
        await self.db.execute(
            "INSERT OR REPLACE INTO groups (group_id, group_title) VALUES (?, ?)",
            (group_id, title)
        )
        await self.db.commit()

    # noinspection SqlNoDataSourceInspection,SqlDialectInspection
    async def get_all_groups(self):
        cursor = await self.db.execute("SELECT * FROM groups")
        return await cursor.fetchall()


db = Database()