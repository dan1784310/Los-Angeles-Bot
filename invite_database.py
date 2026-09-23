"""
Invite Database Module
Handles persistent storage for invite tracking using MongoDB.
"""

import os
import pymongo
from datetime import datetime
from typing import Optional, List, Dict, Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")


class InviteDatabase:
    """Database manager for the invite tracking system with MongoDB."""

    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client["invite_system"]
        self.invites = self.db["invites"]

    def add_invite(self, guild_id: int, inviter_id: int, invited_id: int, invite_code: Optional[str] = None) -> bool:
        """Record that `inviter_id` invited `invited_id` into the guild."""
        try:
            self.invites.insert_one({
                "guild_id": guild_id,
                "inviter_id": inviter_id,
                "invited_id": invited_id,
                "invite_code": invite_code,
                "left": False,
                "created_at": datetime.now().timestamp()
            })
            return True
        except Exception as e:
            print(f"[INVITE DB] Error adding invite: {e}")
            return False

    def mark_left(self, guild_id: int, invited_id: int) -> bool:
        """Mark all active invite records for a departing member as left."""
        try:
            self.invites.update_many(
                {"guild_id": guild_id, "invited_id": invited_id, "left": False},
                {"$set": {"left": True, "left_at": datetime.now().timestamp()}}
            )
            return True
        except Exception as e:
            print(f"[INVITE DB] Error marking member as left: {e}")
            return False

    def get_invite_stats(self, guild_id: int, user_id: int) -> Dict[str, int]:
        """Get total/active/left invite counts for a user."""
        try:
            total = self.invites.count_documents({"guild_id": guild_id, "inviter_id": user_id})
            left = self.invites.count_documents({"guild_id": guild_id, "inviter_id": user_id, "left": True})
            active = total - left
            return {"total": total, "active": active, "left": left}
        except Exception as e:
            print(f"[INVITE DB] Error getting invite stats: {e}")
            return {"total": 0, "active": 0, "left": 0}

    def get_leaderboard(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get the invite leaderboard, ranking inviters by all-time invites."""
        try:
            pipeline = [
                {"$match": {"guild_id": guild_id}},
                {"$group": {
                    "_id": "$inviter_id",
                    "total": {"$sum": 1},
                    "left": {"$sum": {"$cond": ["$left", 1, 0]}}
                }},
                {"$addFields": {"active": {"$subtract": ["$total", "$left"]}}},
                {"$sort": {"total": -1, "active": -1, "_id": 1}}
            ]
            return list(self.invites.aggregate(pipeline))
        except Exception as e:
            print(f"[INVITE DB] Error getting leaderboard: {e}")
            return []

    def close(self):
        if self.client:
            self.client.close()


# Global database instance
db = InviteDatabase()
