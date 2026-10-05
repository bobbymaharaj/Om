"""
Run this locally to generate a Pyrogram user-session string.
Usage:  python gen_session.py
Then copy the printed string and send it to your bot via /addsession
"""
from pyrogram import Client
from config import API_ID, API_HASH

if not API_ID or not API_HASH:
    raise SystemExit("❌ Set API_ID and API_HASH in your .env first.")

with Client("gen", api_id=API_ID, api_hash=API_HASH, in_memory=True) as app:
    print("\n✅ Your session string:\n")
    print(app.export_session_string())
    print("\n⚠️  Treat this string like a password. Never share it.\n")