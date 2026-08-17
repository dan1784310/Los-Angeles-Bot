"""
Giveaway Database Module
Handles all database operations for the giveaway system using SQLite.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import os

# Use absolute path relative to this file to prevent database reset across working directory changes
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "giveaways.db")


class GiveawayDatabase:
    """Database manager for giveaway system."""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database tables."""
        try:
            self.conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            self.conn.execute("PRAGMA foreign_keys = ON;")
            self.cursor = self.conn.cursor()
            self.cursor.row_factory = sqlite3.Row  # Enable row factory for dictionary access
        except Exception as e:
            print(f"[DATABASE] Error initializing database: {e}")
            raise
        
        # Giveaways table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                giveaway_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                host_id INTEGER,
                prize TEXT NOT NULL,
                winners_amount INTEGER NOT NULL,
                end_timestamp REAL NOT NULL,
                giveaway_message TEXT,
                winner_role_id INTEGER,
                winner_dm_message TEXT,
                required_role_id INTEGER,
                requirement_bypass_role_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL
            )
        """)
        
        # Participants table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at REAL NOT NULL,
                UNIQUE(giveaway_id, user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways (giveaway_id) ON DELETE CASCADE
            )
        """)
        
        # Winners table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                won_at REAL NOT NULL,
                FOREIGN KEY (giveaway_id) REFERENCES giveaways (giveaway_id) ON DELETE CASCADE
            )
        """)
        
        # Rigged winners table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_rigged_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id TEXT NOT NULL,
                rigged_user_id INTEGER NOT NULL,
                rigged_by INTEGER NOT NULL,
                rigged_at REAL NOT NULL,
                UNIQUE(giveaway_id, rigged_user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways (giveaway_id) ON DELETE CASCADE
            )
        """)
        
        self.conn.commit()
    
    def create_giveaway(
        self,
        giveaway_id: str,
        guild_id: int,
        channel_id: int,
        message_id: int,
        creator_id: int,
        host_id: Optional[int],
        prize: str,
        winners_amount: int,
        end_timestamp: float,
        giveaway_message: Optional[str] = None,
        winner_role_id: Optional[int] = None,
        winner_dm_message: Optional[str] = None,
        required_role_id: Optional[int] = None,
        requirement_bypass_role_id: Optional[int] = None
    ) -> bool:
        """Create a new giveaway."""
        try:
            self.cursor.execute("""
                INSERT INTO giveaways (
                    giveaway_id, guild_id, channel_id, message_id, creator_id,
                    host_id, prize, winners_amount, end_timestamp, giveaway_message,
                    winner_role_id, winner_dm_message, required_role_id,
                    requirement_bypass_role_id, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """, (
                giveaway_id, guild_id, channel_id, message_id, creator_id,
                host_id, prize, winners_amount, end_timestamp, giveaway_message,
                winner_role_id, winner_dm_message, required_role_id,
                requirement_bypass_role_id, datetime.now().timestamp()
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error creating giveaway: {e}")
            return False
    
    def get_giveaway_by_message_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get giveaway by message ID."""
        try:
            self.cursor.execute("""
                SELECT * FROM giveaways WHERE message_id = ?
            """, (message_id,))
            row = self.cursor.fetchone()
            if row:
                return self._row_to_giveaway_dict(row)
            return None
        except Exception as e:
            print(f"[DATABASE] Error getting giveaway by message ID: {e}")
            return None
    
    def get_giveaway(self, giveaway_id: str) -> Optional[Dict[str, Any]]:
        """Get giveaway by ID."""
        try:
            self.cursor.execute("""
                SELECT * FROM giveaways WHERE giveaway_id = ?
            """, (giveaway_id,))
            row = self.cursor.fetchone()
            if row:
                return self._row_to_giveaway_dict(row)
            return None
        except Exception as e:
            print(f"[DATABASE] Error getting giveaway: {e}")
            return None
    
    def get_active_giveaways(self) -> List[Dict[str, Any]]:
        """Get all active giveaways."""
        try:
            self.cursor.execute("""
                SELECT * FROM giveaways WHERE status = 'active'
            """)
            rows = self.cursor.fetchall()
            return [self._row_to_giveaway_dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting active giveaways: {e}")
            return []
    
    def get_all_giveaways(self) -> List[Dict[str, Any]]:
        """Get all giveaways."""
        try:
            self.cursor.execute("""
                SELECT * FROM giveaways
            """)
            rows = self.cursor.fetchall()
            return [self._row_to_giveaway_dict(row) for row in rows]
        except Exception as e:
            print(f"[DATABASE] Error getting all giveaways: {e}")
            return []
    
    def get_giveaways_by_guild(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get all giveaways for a guild."""
        try:
            self.cursor.execute("""
                SELECT * FROM giveaways WHERE guild_id = ?
            """, (guild_id,))
            rows = self.cursor.fetchall()
            return [self._row_to_giveaway_dict(row) for row in rows]
        except Exception as e:
            print(f"[DATABASE] Error getting guild giveaways: {e}")
            return []
    
    def update_giveaway_status(self, giveaway_id: str, status: str) -> bool:
        """Update giveaway status."""
        try:
            self.cursor.execute("""
                UPDATE giveaways SET status = ? WHERE giveaway_id = ?
            """, (status, giveaway_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error updating giveaway status: {e}")
            return False
    
    def update_giveaway_end_timestamp(self, giveaway_id: str, end_timestamp: float) -> bool:
        """Update giveaway end timestamp."""
        try:
            self.cursor.execute("""
                UPDATE giveaways SET end_timestamp = ? WHERE giveaway_id = ?
            """, (end_timestamp, giveaway_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error updating giveaway end timestamp: {e}")
            return False
    
    def delete_giveaway(self, giveaway_id: str) -> bool:
        """Delete a giveaway and its participants."""
        try:
            self.cursor.execute("DELETE FROM giveaway_winners WHERE giveaway_id = ?", (giveaway_id,))
            self.cursor.execute("DELETE FROM giveaway_participants WHERE giveaway_id = ?", (giveaway_id,))
            self.cursor.execute("DELETE FROM giveaways WHERE giveaway_id = ?", (giveaway_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting giveaway: {e}")
            return False
    
    def add_participant(self, giveaway_id: str, user_id: int) -> bool:
        """Add a participant to a giveaway."""
        try:
            self.cursor.execute("""
                INSERT INTO giveaway_participants (giveaway_id, user_id, joined_at)
                VALUES (?, ?, ?)
            """, (giveaway_id, user_id, datetime.now().timestamp()))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Error adding participant: {e}")
            return False
    
    def remove_participant(self, giveaway_id: str, user_id: int) -> bool:
        """Remove a participant from a giveaway."""
        try:
            self.cursor.execute("""
                DELETE FROM giveaway_participants 
                WHERE giveaway_id = ? AND user_id = ?
            """, (giveaway_id, user_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error removing participant: {e}")
            return False
    
    def has_participant(self, giveaway_id: str, user_id: int) -> bool:
        """Check if user is a participant."""
        try:
            self.cursor.execute("""
                SELECT 1 FROM giveaway_participants 
                WHERE giveaway_id = ? AND user_id = ?
            """, (giveaway_id, user_id))
            return self.cursor.fetchone() is not None
        except Exception as e:
            print(f"Error checking participant: {e}")
            return False
    
    def get_participants(self, giveaway_id: str) -> List[int]:
        """Get all participant user IDs for a giveaway."""
        try:
            self.cursor.execute("""
                SELECT user_id FROM giveaway_participants WHERE giveaway_id = ?
            """, (giveaway_id,))
            rows = self.cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            print(f"Error getting participants: {e}")
            return []
    
    def get_participant_count(self, giveaway_id: str) -> int:
        """Get participant count for a giveaway."""
        try:
            self.cursor.execute("""
                SELECT COUNT(*) FROM giveaway_participants WHERE giveaway_id = ?
            """, (giveaway_id,))
            return self.cursor.fetchone()[0]
        except Exception as e:
            print(f"Error getting participant count: {e}")
            return 0
    
    def add_winner(self, giveaway_id: str, user_id: int) -> bool:
        """Add a winner to a giveaway."""
        try:
            self.cursor.execute("""
                INSERT INTO giveaway_winners (giveaway_id, user_id, won_at)
                VALUES (?, ?, ?)
            """, (giveaway_id, user_id, datetime.now().timestamp()))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding winner: {e}")
            return False
    
    def get_winners(self, giveaway_id: str) -> List[int]:
        """Get all winner user IDs for a giveaway."""
        try:
            self.cursor.execute("""
                SELECT user_id FROM giveaway_winners WHERE giveaway_id = ?
            """, (giveaway_id,))
            rows = self.cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            print(f"Error getting winners: {e}")
            return []
    
    def clear_winners(self, giveaway_id: str) -> bool:
        """Clear all winners for a giveaway."""
        try:
            self.cursor.execute("""
                DELETE FROM giveaway_winners WHERE giveaway_id = ?
            """, (giveaway_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error clearing winners: {e}")
            return False
    
    def add_rigged_winner(self, giveaway_id: str, rigged_user_id: int, rigged_by: int) -> bool:
        """Add a rigged winner to a giveaway."""
        try:
            self.cursor.execute("""
                INSERT INTO giveaway_rigged_winners (giveaway_id, rigged_user_id, rigged_by, rigged_at)
                VALUES (?, ?, ?, ?)
            """, (giveaway_id, rigged_user_id, rigged_by, datetime.now().timestamp()))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Error adding rigged winner: {e}")
            return False
    
    def get_rigged_winner(self, giveaway_id: str) -> Optional[int]:
        """Get the rigged winner for a giveaway."""
        try:
            self.cursor.execute("""
                SELECT rigged_user_id FROM giveaway_rigged_winners WHERE giveaway_id = ?
            """, (giveaway_id,))
            row = self.cursor.fetchone()
            if row:
                return row[0]
            return None
        except Exception as e:
            print(f"Error getting rigged winner: {e}")
            return None
    
    def clear_rigged_winner(self, giveaway_id: str) -> bool:
        """Clear rigged winner for a giveaway."""
        try:
            self.cursor.execute("""
                DELETE FROM giveaway_rigged_winners WHERE giveaway_id = ?
            """, (giveaway_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error clearing rigged winner: {e}")
            return False
    
    def _row_to_giveaway_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        if row is None:
            return None
        return dict(row)
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


# Global database instance
db = GiveawayDatabase()
