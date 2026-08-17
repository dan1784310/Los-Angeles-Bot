"""
Ticket Database Module
Handles all database operations for the ticket system using SQLite.
"""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class TicketDatabase:
    """Database manager for ticket system persistence."""
    
    def __init__(self, db_path: str = "tickets.db"):
        self.db_path = db_path
        self._initialize_database()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _initialize_database(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Guild settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    panel_channel_id INTEGER,
                    ticket_category_id INTEGER,
                    support_roles TEXT,
                    blacklisted_roles TEXT,
                    banner_url TEXT,
                    bottom_banner_url TEXT,
                    text1 TEXT,
                    text2 TEXT,
                    text3 TEXT,
                    text4 TEXT,
                    text5 TEXT,
                    ticket_counter INTEGER DEFAULT 0
                )
            """)

            # Migration: add blacklisted_roles to a pre-existing database
            # that was created before this column existed.
            try:
                cursor.execute("ALTER TABLE guild_settings ADD COLUMN blacklisted_roles TEXT")
            except Exception:
                pass  # Column already exists
            
            # Ticket categories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    name TEXT NOT NULL,
                    title TEXT,
                    description TEXT,
                    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id)
                )
            """)
            
            # Active tickets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    user_id INTEGER,
                    category_id INTEGER,
                    ticket_number INTEGER,
                    status TEXT DEFAULT 'open',
                    claimed_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id),
                    FOREIGN KEY (category_id) REFERENCES ticket_categories(id)
                )
            """)

            # Migration: add claimed_by/issue_text to a pre-existing database
            # that was created before these columns existed.
            try:
                cursor.execute("ALTER TABLE tickets ADD COLUMN claimed_by INTEGER")
            except Exception:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE tickets ADD COLUMN issue_text TEXT")
            except Exception:
                pass  # Column already exists
            
            # Ticket panel messages table (for updating panels)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS panel_messages (
                    guild_id INTEGER PRIMARY KEY,
                    message_id INTEGER,
                    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id)
                )
            """)
    
    # Guild Settings Operations
    
    def save_guild_settings(self, guild_id: int, settings: Dict[str, Any]) -> bool:
        """Save or update guild settings."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO guild_settings 
                    (guild_id, panel_channel_id, ticket_category_id, support_roles, blacklisted_roles,
                     banner_url, bottom_banner_url, text1, text2, text3, text4, text5, ticket_counter)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    guild_id,
                    settings.get('panel_channel_id'),
                    settings.get('ticket_category_id'),
                    json.dumps(settings.get('support_roles', [])),
                    json.dumps(settings.get('blacklisted_roles', [])),
                    settings.get('banner_url'),
                    settings.get('bottom_banner_url'),
                    settings.get('text1'),
                    settings.get('text2'),
                    settings.get('text3'),
                    settings.get('text4'),
                    settings.get('text5'),
                    settings.get('ticket_counter', 0)
                ))
                return True
        except Exception as e:
            print(f"Error saving guild settings: {e}")
            return False
    
    def get_guild_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get guild settings."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'guild_id': row['guild_id'],
                        'panel_channel_id': row['panel_channel_id'],
                        'ticket_category_id': row['ticket_category_id'],
                        'support_roles': json.loads(row['support_roles']) if row['support_roles'] else [],
                        'blacklisted_roles': json.loads(row['blacklisted_roles']) if row['blacklisted_roles'] else [],
                        'banner_url': row['banner_url'],
                        'bottom_banner_url': row['bottom_banner_url'],
                        'text1': row['text1'],
                        'text2': row['text2'],
                        'text3': row['text3'],
                        'text4': row['text4'],
                        'text5': row['text5'],
                        'ticket_counter': row['ticket_counter']
                    }
                return None
        except Exception as e:
            print(f"Error getting guild settings: {e}")
            return None
    
    def has_guild_settings(self, guild_id: int) -> bool:
        """Check if guild has settings configured."""
        return self.get_guild_settings(guild_id) is not None
    
    # Ticket Categories Operations
    
    def save_ticket_category(self, guild_id: int, name: str, title: str, description: str) -> bool:
        """Save a ticket category."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ticket_categories (guild_id, name, title, description)
                    VALUES (?, ?, ?, ?)
                """, (guild_id, name, title, description))
                return True
        except Exception as e:
            print(f"Error saving ticket category: {e}")
            return False
    
    def get_ticket_categories(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get all ticket categories for a guild."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM ticket_categories WHERE guild_id = ?", (guild_id,))
                rows = cursor.fetchall()
                return [
                    {
                        'id': row['id'],
                        'guild_id': row['guild_id'],
                        'name': row['name'],
                        'title': row['title'],
                        'description': row['description']
                    }
                    for row in rows
                ]
        except Exception as e:
            print(f"Error getting ticket categories: {e}")
            return []
    
    def clear_ticket_categories(self, guild_id: int) -> bool:
        """Clear all ticket categories for a guild."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ticket_categories WHERE guild_id = ?", (guild_id,))
                return True
        except Exception as e:
            print(f"Error clearing ticket categories: {e}")
            return False
    
    # Ticket Operations
    
    def create_ticket(self, guild_id: int, channel_id: int, user_id: int, 
                     category_id: int, ticket_number: int, issue_text: Optional[str] = None) -> bool:
        """Create a new ticket record."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO tickets (guild_id, channel_id, user_id, category_id, ticket_number, issue_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (guild_id, channel_id, user_id, category_id, ticket_number, issue_text))
                
                # Increment ticket counter
                cursor.execute("""
                    UPDATE guild_settings SET ticket_counter = ticket_counter + 1
                    WHERE guild_id = ?
                """, (guild_id,))
                return True
        except Exception as e:
            print(f"Error creating ticket: {e}")
            return False
    
    def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get ticket by channel ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row['id'],
                        'guild_id': row['guild_id'],
                        'channel_id': row['channel_id'],
                        'user_id': row['user_id'],
                        'category_id': row['category_id'],
                        'ticket_number': row['ticket_number'],
                        'status': row['status'],
                        'claimed_by': row['claimed_by'],
                        'issue_text': row['issue_text'],
                        'created_at': row['created_at'],
                        'closed_at': row['closed_at']
                    }
                return None
        except Exception as e:
            print(f"Error getting ticket by channel: {e}")
            return None

    def set_ticket_claim(self, channel_id: int, user_id: Optional[int]) -> bool:
        """Set (or clear, with user_id=None) who has claimed a ticket."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tickets SET claimed_by = ?
                    WHERE channel_id = ?
                """, (user_id, channel_id))
                return True
        except Exception as e:
            print(f"Error setting ticket claim: {e}")
            return False
    
    def close_ticket(self, channel_id: int) -> bool:
        """Mark a ticket as closed."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tickets SET status = 'closed', closed_at = CURRENT_TIMESTAMP
                    WHERE channel_id = ?
                """, (channel_id,))
                return True
        except Exception as e:
            print(f"Error closing ticket: {e}")
            return False
    
    def delete_ticket(self, channel_id: int) -> bool:
        """Delete a ticket record."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tickets WHERE channel_id = ?", (channel_id,))
                return True
        except Exception as e:
            print(f"Error deleting ticket: {e}")
            return False
    
    def get_user_open_tickets(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        """Get all open tickets for a user."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM tickets 
                    WHERE guild_id = ? AND user_id = ? AND status = 'open'
                """, (guild_id, user_id))
                rows = cursor.fetchall()
                return [
                    {
                        'id': row['id'],
                        'guild_id': row['guild_id'],
                        'channel_id': row['channel_id'],
                        'user_id': row['user_id'],
                        'category_id': row['category_id'],
                        'ticket_number': row['ticket_number'],
                        'status': row['status'],
                        'created_at': row['created_at'],
                        'closed_at': row['closed_at']
                    }
                    for row in rows
                ]
        except Exception as e:
            print(f"Error getting user open tickets: {e}")
            return []
    
    # Panel Message Operations
    
    def save_panel_message(self, guild_id: int, message_id: int) -> bool:
        """Save the panel message ID for a guild."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO panel_messages (guild_id, message_id)
                    VALUES (?, ?)
                """, (guild_id, message_id))
                return True
        except Exception as e:
            print(f"Error saving panel message: {e}")
            return False
    
    def get_panel_message(self, guild_id: int) -> Optional[int]:
        """Get the panel message ID for a guild."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT message_id FROM panel_messages WHERE guild_id = ?", (guild_id,))
                row = cursor.fetchone()
                return row['message_id'] if row else None
        except Exception as e:
            print(f"Error getting panel message: {e}")
            return None
    
    def clear_panel_message(self, guild_id: int) -> bool:
        """Clear the panel message for a guild."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM panel_messages WHERE guild_id = ?", (guild_id,))
                return True
        except Exception as e:
            print(f"Error clearing panel message: {e}")
            return False


# Global database instance
db = TicketDatabase()
