"""
Moderation Database Module
Handles persistent storage for warnings and moderation logs.
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

class ModerationDatabase:
    """Database for moderation actions and warnings."""
    
    def __init__(self, db_path: str = "moderation.db"):
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Warnings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Moderation logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS modlogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                reason TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Channel locks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL UNIQUE,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: Optional[str] = None) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, reason)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[MOD DB] Error adding warning: {e}")
            return False
        finally:
            conn.close()
    
    def get_warnings(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
                (guild_id, user_id)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[MOD DB] Error getting warnings: {e}")
            return []
        finally:
            conn.close()
    
    def get_warning_count(self, guild_id: int, user_id: int) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) as count FROM warnings WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            return cursor.fetchone()['count']
        except Exception as e:
            print(f"[MOD DB] Error getting warning count: {e}")
            return 0
        finally:
            conn.close()
    
    def add_modlog(self, guild_id: int, user_id: int, moderator_id: int, action_type: str, 
                   reason: Optional[str] = None, details: Optional[str] = None) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO modlogs (guild_id, user_id, moderator_id, action_type, reason, details) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, action_type, reason, details)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[MOD DB] Error adding modlog: {e}")
            return False
        finally:
            conn.close()
    
    def get_modlogs(self, guild_id: int, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM modlogs WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT ?",
                (guild_id, user_id, limit)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[MOD DB] Error getting modlogs: {e}")
            return []
        finally:
            conn.close()
    
    def set_channel_lock(self, guild_id: int, channel_id: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO channel_locks (guild_id, channel_id, locked_at) VALUES (?, ?, ?)",
                (guild_id, channel_id, datetime.now().isoformat())
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[MOD DB] Error setting channel lock: {e}")
            return False
        finally:
            conn.close()
    
    def remove_channel_lock(self, guild_id: int, channel_id: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM channel_locks WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[MOD DB] Error removing channel lock: {e}")
            return False
        finally:
            conn.close()
    
    def is_channel_locked(self, guild_id: int, channel_id: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM channel_locks WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            print(f"[MOD DB] Error checking channel lock: {e}")
            return False
        finally:
            conn.close()

# Global database instance
db = ModerationDatabase()
