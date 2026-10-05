# Render deployment

## Required Render settings

Use the **Python** runtime. Set this environment variable in the Render service:

- `PYTHON_VERSION=3.11.11`

The repository also contains `.python-version` with `3.11.11` as a second, source-controlled safeguard.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
python bot.py
```

Required environment variables:

- `BOT_TOKEN`
- `API_ID`
- `API_HASH`
- `ADMIN_ID`
- `MONGO_URI`
- `OWNER_CREDIT` (optional)
- `BOT_NAME` (optional)

## Why Python 3.11 is required

Pyrogram 2.0.106 uses synchronous asyncio APIs during import. Python 3.14 changed `asyncio.get_event_loop()` so it raises when no current event loop exists. That causes the startup traceback seen on Render. This project should therefore run on Python 3.11 rather than Render's current 3.14 default.
