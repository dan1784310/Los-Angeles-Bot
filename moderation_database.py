"""
Moderation Database Module
Handles persistent storage for warnings and moderation logs using MongoDB.
"""

import os
import pymongo
from datetime import datetime
from typing import Optional, List, Dict, Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

class ModerationDatabase:
    """Database manager for moderation system with MongoDB."""
    
    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client["moderation_system"]
        self.warnings = self.db["warnings"]
        self.modlogs = self.db["modlogs"]
        self.channel_locks = self.db["channel_locks"]
    
    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: Optional[str] = None) -> bool:
        try:
            self.warnings.insert_one({
                "guild_id": guild_id,
                "user_id": user_id,
                "moderator_id": moderator_id,
                "reason": reason,
                "created_at": datetime.now().timestamp()
            })
            return True
        except Exception as e:
            print(f"[MOD DB] Error adding warning: {e}")
            return False
    
    def get_warnings(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        try:
            docs = self.warnings.find({"guild_id": guild_id, "user_id": user_id}).sort("created_at", -1)
            return list(docs)
        except Exception as e:
            print(f"[MOD DB] Error getting warnings: {e}")
            return []
    
    def get_warning_count(self, guild_id: int, user_id: int) -> int:
        try:
            return self.warnings.count_documents({"guild_id": guild_id, "user_id": user_id})
        except Exception as e:
            print(f"[MOD DB] Error getting warning count: {e}")
            return 0
    
    def add_modlog(self, guild_id: int, user_id: int, moderator_id: int, action_type: str, 
                   reason: Optional[str] = None, details: Optional[str] = None) -> bool:
        try:
            self.modlogs.insert_one({
                "guild_id": guild_id,
                "user_id": user_id,
                "moderator_id": moderator_id,
                "action_type": action_type,
                "reason": reason,
                "details": details,
                "created_at": datetime.now().timestamp()
            })
            return True
        except Exception as e:
            print(f"[MOD DB] Error adding modlog: {e}")
            return False
    
    def get_modlogs(self, guild_id: int, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            docs = self.modlogs.find({"guild_id": guild_id, "user_id": user_id}).sort("created_at", -1).limit(limit)
            return list(docs)
        except Exception as e:
            print(f"[MOD DB] Error getting modlogs: {e}")
            return []
    
    def set_channel_lock(self, guild_id: int, channel_id: int) -> bool:
        try:
            self.channel_locks.update_one(
                {"guild_id": guild_id, "channel_id": channel_id},
                {"$set": {"locked_at": datetime.now().timestamp()}},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"[MOD DB] Error setting channel lock: {e}")
            return False
    
    def remove_channel_lock(self, guild_id: int, channel_id: int) -> bool:
        try:
            self.channel_locks.delete_one({"guild_id": guild_id, "channel_id": channel_id})
            return True
        except Exception as e:
            print(f"[MOD DB] Error removing channel lock: {e}")
            return False
    
    def is_channel_locked(self, guild_id: int, channel_id: int) -> bool:
        try:
            return self.channel_locks.find_one({"guild_id": guild_id, "channel_id": channel_id}) is not None
        except Exception as e:
            print(f"[MOD DB] Error checking channel lock: {e}")
            return False
    
    def close(self):
        if self.client:
            self.client.close()

# Global database instance
db = ModerationDatabase()
