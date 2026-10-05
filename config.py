import os

# Automatically load variables from .env (ignored in production)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def env(key, default=""):
    return os.environ.get(key, default)


BOT_TOKEN = env("BOT_TOKEN")
API_ID = int(env("API_ID", "0") or 0)
API_HASH = env("API_HASH")
ADMIN_ID = int(env("ADMIN_ID", "0") or 0)
MONGO_URI = env("MONGO_URI")  # REQUIRED
OWNER_CREDIT = env("OWNER_CREDIT", "Bobby Maharaj")
BOT_NAME = env("BOT_NAME", "Mass Report Bot")