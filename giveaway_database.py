"""
Giveaway Database Module
Handles all database operations for the giveaway system using MongoDB Atlas.
"""

import os
import pymongo
from datetime import datetime
from typing import Optional, List, Dict, Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

class GiveawayDatabase:
    """Database manager for giveaway system with MongoDB Atlas."""
    
    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client["giveaway_system"]
        self.giveaways = self.db["giveaways"]
        self.participants = self.db["participants"]
        self.winners = self.db["winners"]
        self.rigged_winners = self.db["rigged_winners"]

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
        try:
            self.giveaways.insert_one({
                "giveaway_id": giveaway_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "message_id": message_id,
                "creator_id": creator_id,
                "host_id": host_id,
                "prize": prize,
                "winners_amount": winners_amount,
                "end_timestamp": end_timestamp,
                "giveaway_message": giveaway_message,
                "winner_role_id": winner_role_id,
                "winner_dm_message": winner_dm_message,
                "required_role_id": required_role_id,
                "requirement_bypass_role_id": requirement_bypass_role_id,
                "status": "active",
                "created_at": datetime.now().timestamp()
            })
            return True
        except Exception as e:
            print(f"Error creating giveaway: {e}")
            return False

    def get_giveaway_by_message_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        return self.giveaways.find_one({"message_id": message_id})

    def get_giveaway(self, giveaway_id: str) -> Optional[Dict[str, Any]]:
        return self.giveaways.find_one({"giveaway_id": giveaway_id})

    def get_active_giveaways(self) -> List[Dict[str, Any]]:
        return list(self.giveaways.find({"status": "active"}))

    def get_all_giveaways(self) -> List[Dict[str, Any]]:
        return list(self.giveaways.find({}))

    def get_giveaways_by_guild(self, guild_id: int) -> List[Dict[str, Any]]:
        return list(self.giveaways.find({"guild_id": guild_id}))

    def update_giveaway_status(self, giveaway_id: str, status: str) -> bool:
        res = self.giveaways.update_one({"giveaway_id": giveaway_id}, {"$set": {"status": status}})
        return res.modified_count > 0

    def update_giveaway_end_timestamp(self, giveaway_id: str, end_timestamp: float) -> bool:
        res = self.giveaways.update_one({"giveaway_id": giveaway_id}, {"$set": {"end_timestamp": end_timestamp}})
        return res.modified_count > 0

    def delete_giveaway(self, giveaway_id: str) -> bool:
        self.winners.delete_many({"giveaway_id": giveaway_id})
        self.participants.delete_many({"giveaway_id": giveaway_id})
        self.rigged_winners.delete_many({"giveaway_id": giveaway_id})
        res = self.giveaways.delete_one({"giveaway_id": giveaway_id})
        return res.deleted_count > 0

    def add_participant(self, giveaway_id: str, user_id: int) -> bool:
        try:
            self.participants.update_one(
                {"giveaway_id": giveaway_id, "user_id": user_id},
                {"$setOnInsert": {"joined_at": datetime.now().timestamp()}},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Error adding participant: {e}")
            return False

    def remove_participant(self, giveaway_id: str, user_id: int) -> bool:
        res = self.participants.delete_one({"giveaway_id": giveaway_id, "user_id": user_id})
        return res.deleted_count > 0

    def has_participant(self, giveaway_id: str, user_id: int) -> bool:
        return self.participants.find_one({"giveaway_id": giveaway_id, "user_id": user_id}) is not None

    def get_participants(self, giveaway_id: str) -> List[int]:
        docs = self.participants.find({"giveaway_id": giveaway_id})
        return [doc["user_id"] for doc in docs]

    def get_participant_count(self, giveaway_id: str) -> int:
        return self.participants.count_documents({"giveaway_id": giveaway_id})

    def add_winner(self, giveaway_id: str, user_id: int) -> bool:
        self.winners.insert_one({"giveaway_id": giveaway_id, "user_id": user_id, "won_at": datetime.now().timestamp()})
        return True

    def get_winners(self, giveaway_id: str) -> List[int]:
        docs = self.winners.find({"giveaway_id": giveaway_id})
        return [doc["user_id"] for doc in docs]

    def clear_winners(self, giveaway_id: str) -> bool:
        self.winners.delete_many({"giveaway_id": giveaway_id})
        return True

    def add_rigged_winner(self, giveaway_id: str, rigged_user_id: int, rigged_by: int) -> bool:
        self.rigged_winners.update_one(
            {"giveaway_id": giveaway_id},
            {"$set": {"rigged_user_id": rigged_user_id, "rigged_by": rigged_by, "rigged_at": datetime.now().timestamp()}},
            upsert=True
        )
        return True

    def get_rigged_winner(self, giveaway_id: str) -> Optional[int]:
        doc = self.rigged_winners.find_one({"giveaway_id": giveaway_id})
        return doc["rigged_user_id"] if doc else None

    def clear_rigged_winner(self, giveaway_id: str) -> bool:
        self.rigged_winners.delete_one({"giveaway_id": giveaway_id})
        return True

    def close(self):
        if self.client:
            self.client.close()

db = GiveawayDatabase()
