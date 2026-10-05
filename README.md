# 🤖 Mass Report Bot

Telegram Channel Mass Reporting Bot — Powered by Pyrogram + MongoDB.

💎 **Credits:** Bobby Maharaj

---

## 🗄️ Storage

**MongoDB only.** No JSON fallback. The bot exits on startup if `MONGO_URI`
is missing or unreachable.

Create a free cluster at https://www.mongodb.com/atlas:
1. **Database Access** → add user (read/write to any database)
2. **Network Access** → allow `0.0.0.0/0`
3. **Connect → Drivers → Python** → copy the URI
4. Replace `<password>` with the real one and append the DB name:
   `.../mass_report_bot?retryWrites=true&w=majority`

---

## 🚀 Deploy on Render (Free)

1. Push this repo to GitHub (`.env` is gitignored).
2. https://dashboard.render.com → **New → Web Service** → connect repo.
3. Render reads `render.yaml`. If not, set manually:
   - **Runtime:** Python
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `python bot.py`
4. Set **Environment**:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | from [@BotFather](https://t.me/BotFather) |
| `API_ID` | from https://my.telegram.org |
| `API_HASH` | from https://my.telegram.org |
| `ADMIN_ID` | your numeric ID from [@userinfobot](https://t.me/userinfobot) |
| `MONGO_URI` | **required** — MongoDB Atlas URI |
| `OWNER_CREDIT` | `Bobby Maharaj` |
| `BOT_NAME` | `Mass Report Bot` |

5. Deploy. Logs should show `✅ Connected to MongoDB` and `🤖 Bot started successfully.`

**Keep-alive on free tier:** add [UptimeRobot](https://uptimerobot.com) HTTP monitor
on `https://your-app.onrender.com/healthz`, every 5 minutes.

---

## 🛠 Bot Commands

**User:**
- `/start` — Welcome menu
- `/report @channel` — Start a mass report
- `/help` — How-to guide
- `/about` — Bot info

**Admin only:**
- `/panel` — Admin control panel
- `/stats` — Bot statistics
- `/broadcast` — Broadcast to all users
- `/addsession <string>` — Add a Pyrogram user session
- `/delsession <index>` — Remove a session
- `/ban <user_id>` / `/unban <user_id>`
- `/cancel` — Cancel pending admin action

---

## 🖥️ Run Locally

```bash
python -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # fill in values
python gen_session.py            # optional — generate a user session
python bot.py