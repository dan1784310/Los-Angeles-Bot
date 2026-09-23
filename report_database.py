"""
Persistent storage helpers for the interactive report system.
"""

import os

import pymongo
from pymongo import ReturnDocument

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")


class ReportDatabase:
    """Stores atomic per-guild further-review ticket numbers."""

    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client["report_system"]
        self.sequences = self.db["report_sequences"]

    def next_report_number(self, guild_id: int) -> int:
        """Atomically return the next Report-N number for a guild."""
        document = self.sequences.find_one_and_update(
            {"_id": guild_id},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(document["value"])

    def close(self) -> None:
        self.client.close()


db = ReportDatabase()
