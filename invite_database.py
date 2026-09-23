"""
Invite Database Module
Handles persistent storage for invite tracking using MongoDB.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pymongo
from pymongo import UpdateOne

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
BACKFILL_VERSION = 1


class InviteDatabase:
    """Database manager for the invite tracking system with MongoDB."""

    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client["invite_system"]
        self.invites = self.db["invites"]
        self.metadata = self.db["metadata"]

    @staticmethod
    def _event_id(
        guild_id: int,
        invited_id: int,
        joined_at_ms: Optional[int],
    ) -> str:
        join_key = joined_at_ms if joined_at_ms is not None else "unknown"
        return f"{guild_id}:{invited_id}:{join_key}"

    def add_invite(
        self,
        guild_id: int,
        inviter_id: int,
        invited_id: int,
        invite_code: Optional[str] = None,
        joined_at: Optional[float] = None,
    ) -> bool:
        """Record that `inviter_id` invited `invited_id` into the guild."""
        joined_at_ms = (
            int(joined_at * 1000) if joined_at is not None else None
        )
        record = {
            "guild_id": guild_id,
            "inviter_id": inviter_id,
            "invited_id": invited_id,
            "invite_code": invite_code,
            "source_invite_code": invite_code,
            "join_source_type": 5,
            "joined_at": joined_at,
            "left": False,
            "backfilled": False,
            "created_at": datetime.now().timestamp(),
        }

        try:
            if joined_at_ms is None:
                self.invites.insert_one(record)
            else:
                # A member can generate the same join event more than once if
                # Discord replays/resumes events. The deterministic ID makes
                # live tracking and later historical backfills idempotent.
                self.invites.update_one(
                    {"_id": self._event_id(guild_id, invited_id, joined_at_ms)},
                    {"$setOnInsert": record},
                    upsert=True,
                )
            return True
        except Exception as e:
            print(f"[INVITE DB] Error adding invite: {e}")
            return False

    def backfill_invites(
        self,
        guild_id: int,
        records: List[Dict[str, Any]],
    ) -> int:
        """Merge historical member-search results with live invite records."""
        if not records:
            return 0

        invited_ids = [int(record["invited_id"]) for record in records]
        existing_records = list(
            self.invites.find(
                {
                    "guild_id": guild_id,
                    "invited_id": {"$in": invited_ids},
                }
            )
        )
        existing_by_member: Dict[int, List[Dict[str, Any]]] = {}
        for existing in existing_records:
            existing_by_member.setdefault(
                int(existing["invited_id"]),
                [],
            ).append(existing)

        used_existing_ids = set()
        operations = []

        for record in records:
            invited_id = int(record["invited_id"])
            joined_at = record.get("joined_at")
            joined_at_ms = record.get("joined_at_ms")
            event_id = self._event_id(guild_id, invited_id, joined_at_ms)

            closest_match = None
            closest_difference = float("inf")
            if joined_at is not None:
                for existing in existing_by_member.get(invited_id, []):
                    if existing["_id"] in used_existing_ids:
                        continue

                    existing_joined_at = existing.get("joined_at")
                    if existing_joined_at is None:
                        existing_joined_at = existing.get("created_at")
                    if existing_joined_at is None:
                        continue

                    try:
                        difference = abs(
                            float(existing_joined_at) - joined_at
                        )
                    except (TypeError, ValueError):
                        continue
                    if difference <= 600 and difference < closest_difference:
                        closest_match = existing
                        closest_difference = difference

            if closest_match is not None:
                used_existing_ids.add(closest_match["_id"])
                operations.append(
                    UpdateOne(
                        {"_id": closest_match["_id"]},
                        {
                            "$set": {
                                "inviter_id": int(record["inviter_id"]),
                                "invite_code": record.get("invite_code"),
                                "source_invite_code": record.get(
                                    "invite_code"
                                ),
                                "join_source_type": record.get(
                                    "join_source_type"
                                ),
                                "joined_at": joined_at,
                                "left": False,
                                "backfilled": True,
                            },
                            "$unset": {"left_at": ""},
                        },
                    )
                )
                continue

            historical_record = {
                "_id": event_id,
                "guild_id": guild_id,
                "inviter_id": int(record["inviter_id"]),
                "invited_id": invited_id,
                "invite_code": record.get("invite_code"),
                "source_invite_code": record.get("invite_code"),
                "join_source_type": record.get("join_source_type"),
                "join_source_application_id": record.get(
                    "join_source_application_id"
                ),
                "join_source_channel_id": record.get(
                    "join_source_channel_id"
                ),
                "joined_at": joined_at,
                "left": False,
                "backfilled": True,
                "created_at": datetime.now().timestamp(),
            }
            operations.append(
                UpdateOne(
                    {"_id": event_id},
                    {"$setOnInsert": historical_record},
                    upsert=True,
                )
            )

        if not operations:
            return 0

        try:
            self.invites.bulk_write(operations, ordered=False)
            return len(operations)
        except Exception as e:
            print(f"[INVITE DB] Error backfilling invites: {e}")
            return 0

    def mark_left(self, guild_id: int, invited_id: int) -> bool:
        """Mark all active invite records for a departing member as left."""
        try:
            self.invites.update_many(
                {
                    "guild_id": guild_id,
                    "invited_id": invited_id,
                    "left": False,
                },
                {
                    "$set": {
                        "left": True,
                        "left_at": datetime.now().timestamp(),
                    }
                },
            )
            return True
        except Exception as e:
            print(f"[INVITE DB] Error marking member as left: {e}")
            return False

    def get_invite_stats(self, guild_id: int, user_id: int) -> Dict[str, int]:
        """Get total/active/left invite counts for a user."""
        try:
            total = self.invites.count_documents(
                {"guild_id": guild_id, "inviter_id": user_id}
            )
            left = self.invites.count_documents(
                {
                    "guild_id": guild_id,
                    "inviter_id": user_id,
                    "left": True,
                }
            )
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
                {
                    "$group": {
                        "_id": "$inviter_id",
                        "total": {"$sum": 1},
                        "left": {
                            "$sum": {"$cond": ["$left", 1, 0]}
                        },
                    }
                },
                {
                    "$addFields": {
                        "active": {"$subtract": ["$total", "$left"]}
                    }
                },
                {"$sort": {"total": -1, "active": -1, "_id": 1}},
            ]
            return list(self.invites.aggregate(pipeline))
        except Exception as e:
            print(f"[INVITE DB] Error getting leaderboard: {e}")
            return []

    def is_backfill_complete(self, guild_id: int) -> bool:
        """Return whether the current historical backfill has completed."""
        try:
            document = self.metadata.find_one(
                {
                    "_id": f"invite_backfill:{guild_id}",
                    "version": BACKFILL_VERSION,
                    "complete": True,
                }
            )
            return document is not None
        except Exception as e:
            print(f"[INVITE DB] Error reading backfill status: {e}")
            return False

    def mark_backfill_complete(
        self,
        guild_id: int,
        imported_count: int,
    ) -> bool:
        """Persist completion so historical backfill only runs once."""
        try:
            self.metadata.update_one(
                {"_id": f"invite_backfill:{guild_id}"},
                {
                    "$set": {
                        "version": BACKFILL_VERSION,
                        "complete": True,
                        "imported_count": imported_count,
                        "completed_at": datetime.now().timestamp(),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as e:
            print(f"[INVITE DB] Error saving backfill status: {e}")
            return False

    def close(self):
        if self.client:
            self.client.close()


# Global database instance
db = InviteDatabase()
