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

    def get_guild_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        return self.guild_settings.find_one({"guild_id": guild_id})

    def set_guild_settings(self, guild_id: int, ticket_category_id: int, 
                           transcript_channel_id: int, blacklisted_roles: List[int], 
                           support_roles: List[int]):
        self.guild_settings.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "ticket_category_id": ticket_category_id,
                    "transcript_channel_id": transcript_channel_id,
                    "blacklisted_roles": blacklisted_roles,
                    "support_roles": support_roles
                },
                "$setOnInsert": {"ticket_counter": 0}
            },
            upsert=True
        )

    def add_category(self, guild_id: int, name: str, emoji: Optional[str] = None, 
                     description: Optional[str] = None, title: Optional[str] = None) -> int:
        cat_id = self.categories.count_documents({"guild_id": guild_id}) + 1
        self.categories.insert_one({
            "id": cat_id,
            "guild_id": guild_id,
            "name": name,
            "emoji": emoji,
            "description": description,
            "title": title
        })
        return cat_id

    def get_ticket_categories(self, guild_id: int) -> List[Dict[str, Any]]:
        return list(self.categories.find({"guild_id": guild_id}))

    def delete_category(self, guild_id: int, category_id: int) -> bool:
        res = self.categories.delete_one({"guild_id": guild_id, "id": category_id})
        return res.deleted_count > 0

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
        return self.tickets.find_one({"channel_id": channel_id})

    def get_user_open_tickets(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        return list(self.tickets.find({"guild_id": guild_id, "user_id": user_id, "status": "open"}))

    def set_ticket_claim(self, channel_id: int, user_id: Optional[int]):
        self.tickets.update_one({"channel_id": channel_id}, {"$set": {"claimed_by": user_id}})

    def close_ticket(self, channel_id: int):
        self.tickets.update_one({"channel_id": channel_id}, {"$set": {"status": "closed"}})

    def delete_ticket(self, channel_id: int):
        self.tickets.delete_one({"channel_id": channel_id})

db = TicketDatabase()
