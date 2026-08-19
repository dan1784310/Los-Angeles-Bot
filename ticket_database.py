"""
Ticket Database Module
Handles all database operations for the ticket system using MongoDB Atlas.
"""

import os
import pymongo
from typing import Optional, List, Dict, Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")


class TicketDatabase:
    """Database manager for ticket system using MongoDB Atlas."""

    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client["ticket_system"]
        self.guild_settings = self.db["guild_settings"]
        self.categories = self.db["categories"]
        self.tickets = self.db["tickets"]

    # ==========================================
    # Guild settings
    # ==========================================

    def has_guild_settings(self, guild_id: int) -> bool:
        """Whether this guild has a ticket system configured at all."""
        return self.guild_settings.find_one({"guild_id": guild_id}, {"_id": 1}) is not None

    def get_guild_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        return self.guild_settings.find_one({"guild_id": guild_id}, {"_id": 0})

    def save_guild_settings(self, guild_id: int, settings: Dict[str, Any]) -> bool:
        """Upsert the guild's ticket settings. `settings` is merged in as-is
        (e.g. panel_channel_id, ticket_category_id, support_roles,
        blacklisted_roles, banner_url, bottom_banner_url, text1-text5,
        ticket_counter)."""
        try:
            self.guild_settings.update_one(
                {"guild_id": guild_id},
                {"$set": settings},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Error saving guild settings: {e}")
            return False

    def set_guild_settings(self, guild_id: int, ticket_category_id: int,
                           transcript_channel_id: int, blacklisted_roles: List[int],
                           support_roles: List[int]) -> bool:
        """Legacy/partial settings updater kept for backwards compatibility."""
        return self.save_guild_settings(guild_id, {
            "ticket_category_id": ticket_category_id,
            "transcript_channel_id": transcript_channel_id,
            "blacklisted_roles": blacklisted_roles,
            "support_roles": support_roles
        })

    # ==========================================
    # Panel message tracking
    # ==========================================

    def get_panel_message(self, guild_id: int) -> Optional[int]:
        settings = self.guild_settings.find_one({"guild_id": guild_id}, {"panel_message_id": 1})
        return settings.get("panel_message_id") if settings else None

    def save_panel_message(self, guild_id: int, message_id: int) -> bool:
        try:
            self.guild_settings.update_one(
                {"guild_id": guild_id},
                {"$set": {"panel_message_id": message_id}},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Error saving panel message: {e}")
            return False

    def clear_panel_message(self, guild_id: int) -> bool:
        try:
            self.guild_settings.update_one(
                {"guild_id": guild_id},
                {"$unset": {"panel_message_id": ""}}
            )
            return True
        except Exception as e:
            print(f"Error clearing panel message: {e}")
            return False

    # ==========================================
    # Ticket categories
    # ==========================================

    def get_ticket_categories(self, guild_id: int) -> List[Dict[str, Any]]:
        return list(self.categories.find({"guild_id": guild_id}, {"_id": 0}))

    def save_ticket_category(self, guild_id: int, name: str,
                             title: Optional[str] = None, description: Optional[str] = None) -> int:
        """Add a new ticket category for this guild, returning its sequential id."""
        cat_id = self.categories.count_documents({"guild_id": guild_id}) + 1
        self.categories.insert_one({
            "id": cat_id,
            "guild_id": guild_id,
            "name": name,
            "title": title,
            "description": description
        })
        return cat_id

    # Kept as an alias — some older call sites use this name.
    def add_category(self, guild_id: int, name: str, emoji: Optional[str] = None,
                     description: Optional[str] = None, title: Optional[str] = None) -> int:
        return self.save_ticket_category(guild_id, name, title=title, description=description)

    def clear_ticket_categories(self, guild_id: int) -> bool:
        try:
            self.categories.delete_many({"guild_id": guild_id})
            return True
        except Exception as e:
            print(f"Error clearing ticket categories: {e}")
            return False

    def delete_category(self, guild_id: int, category_id: int) -> bool:
        res = self.categories.delete_one({"guild_id": guild_id, "id": category_id})
        return res.deleted_count > 0

    # ==========================================
    # Tickets
    # ==========================================

    def create_ticket(self, guild_id: int, channel_id: int, user_id: int,
                      category_id: int, ticket_number: int, issue_text: Optional[str] = None) -> bool:
        self.tickets.insert_one({
            "guild_id": guild_id,
            "channel_id": channel_id,
            "user_id": user_id,
            "category_id": category_id,
            "ticket_number": ticket_number,
            "issue_text": issue_text,
            "status": "open",
            "claimed_by": None
        })
        self.guild_settings.update_one({"guild_id": guild_id}, {"$inc": {"ticket_counter": 1}})
        return True

    def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        return self.tickets.find_one({"channel_id": channel_id}, {"_id": 0})

    def get_user_open_tickets(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        return list(self.tickets.find(
            {"guild_id": guild_id, "user_id": user_id, "status": "open"}, {"_id": 0}
        ))

    def set_ticket_claim(self, channel_id: int, user_id: Optional[int]) -> bool:
        self.tickets.update_one({"channel_id": channel_id}, {"$set": {"claimed_by": user_id}})
        return True

    def set_ticket_transcript_message(self, channel_id: int, message_id: Optional[int]) -> bool:
        """Track the message ID of the live in-channel transcript so it can be edited in place."""
        self.tickets.update_one({"channel_id": channel_id}, {"$set": {"transcript_message_id": message_id}})
        return True

    def close_ticket(self, channel_id: int) -> bool:
        self.tickets.update_one({"channel_id": channel_id}, {"$set": {"status": "closed"}})
        return True

    def delete_ticket(self, channel_id: int) -> bool:
        self.tickets.delete_one({"channel_id": channel_id})
        return True

    def close(self):
        if self.client:
            self.client.close()


db = TicketDatabase()
