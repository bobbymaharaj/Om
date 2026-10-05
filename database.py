"""
MongoDB-only storage backend for the Mass Report Bot.
Requires MONGO_URI in .env / environment variables.
"""

import time

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from config import MONGO_URI


class Database:
    def __init__(self):
        if not MONGO_URI:
            raise SystemExit(
                "❌ MONGO_URI is required.\n"
                "   Get a free cluster at https://www.mongodb.com/atlas\n"
                "   Then set MONGO_URI in your .env / environment variables."
            )

        # ---------- Connect with retries ----------
        self.client = None
        last_err = None
        for attempt in range(1, 4):
            try:
                self.client = MongoClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=8000,
                    connectTimeoutMS=8000,
                    socketTimeoutMS=20000,
                    maxPoolSize=50,
                    retryWrites=True,
                    appname="mass-report-bot",
                )
                # Force a round-trip to verify the connection works
                self.client.admin.command("ping")
                last_err = None
                break
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                last_err = e
                print(f"⚠️ MongoDB connect attempt {attempt}/3 failed: {e}")
                time.sleep(2 * attempt)

        if last_err is not None or self.client is None:
            raise SystemExit(
                f"❌ Could not connect to MongoDB after 3 attempts:\n   {last_err}\n"
                "   Check your MONGO_URI and Atlas IP whitelist (allow 0.0.0.0/0)."
            )

        db = self.client["mass_report_bot"]
        self.users_col = db["users"]
        self.sessions_col = db["sessions"]
        self.reports_col = db["reports"]

        # ---------- Indexes ----------
        try:
            self.sessions_col.create_index([("_id", ASCENDING)], unique=True)
            self.reports_col.create_index([("time", ASCENDING)])
            self.reports_col.create_index([("by", ASCENDING)])
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")

        print("✅ Connected to MongoDB")

    # ---------------- users ----------------
    def add_user(self, user_id, name):
        self.users_col.update_one(
            {"_id": user_id},
            {
                "$set": {"name": name, "last_seen": int(time.time())},
                "$setOnInsert": {"banned": False, "joined": int(time.time())},
            },
            upsert=True,
        )

    def get_users(self):
        return [doc["_id"] for doc in self.users_col.find({}, {"_id": 1})]

    def total_users(self):
        return self.users_col.count_documents({})

    def is_banned(self, user_id):
        doc = self.users_col.find_one({"_id": user_id}, {"banned": 1})
        return bool(doc and doc.get("banned"))

    def ban_user(self, user_id):
        self.users_col.update_one(
            {"_id": user_id}, {"$set": {"banned": True}}, upsert=True
        )

    def unban_user(self, user_id):
        self.users_col.update_one(
            {"_id": user_id}, {"$set": {"banned": False}}, upsert=True
        )

    # ---------------- sessions ----------------
    def add_session(self, session_string):
        """Insert a session string if not already present. Returns True if newly added."""
        session_string = session_string.strip()
        if not session_string:
            return False
        res = self.sessions_col.update_one(
            {"_id": session_string},
            {"$setOnInsert": {"added": int(time.time())}},
            upsert=True,
        )
        return res.upserted_id is not None

    def get_sessions(self):
        return [doc["_id"] for doc in self.sessions_col.find({}, {"_id": 1})]

    def del_session(self, session_string):
        res = self.sessions_col.delete_one({"_id": session_string})
        return res.deleted_count > 0

    def total_sessions(self):
        return self.sessions_col.count_documents({})

    # ---------------- reports ----------------
    def add_report(self, target, count, by):
        self.reports_col.insert_one(
            {
                "target": target,
                "reports": count,
                "by": by,
                "time": int(time.time()),
            }
        )

    def total_reports(self):
        return self.reports_col.count_documents({})

    def total_report_count(self):
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$reports"}}}]
        res = list(self.reports_col.aggregate(pipeline))
        return res[0]["total"] if res else 0

    # ---------------- health ----------------
    def ping(self):
        """Returns True if MongoDB is reachable."""
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False