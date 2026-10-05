"""
MASS REPORT BOT — Telegram Channel Mass Reporting Bot
Credits: Bobby Maharaj
Storage: MongoDB (required)
Hosted on: Render (Free)
"""

import asyncio
import os
import threading
import time

from flask import Flask

from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait
from pyrogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from pyrogram.raw.functions.messages import Report, ReportSpam
from pyrogram.raw.types import (
    InputReportReasonChildAbuse,
    InputReportReasonCopyright,
    InputReportReasonFake,
    InputReportReasonOther,
    InputReportReasonPornography,
    InputReportReasonSpam,
    InputReportReasonViolence,
)

from config import (
    BOT_TOKEN,
    API_ID,
    API_HASH,
    ADMIN_ID,
    MONGO_URI,
    OWNER_CREDIT,
)
from database import Database

# ---------------- CONFIG CHECK ----------------
if not BOT_TOKEN or not API_ID or not API_HASH or not ADMIN_ID or not MONGO_URI:
    raise SystemExit(
        "❌ Missing env vars!\n"
        "   Required: BOT_TOKEN, API_ID, API_HASH, ADMIN_ID, MONGO_URI"
    )

db = Database()

# ---------------- PYROGRAM BOT ----------------
app = Client(
    "mass_report_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    workers=16,
)

# ---------------- FLASK KEEP-ALIVE (Render) ----------------
flask_app = Flask(__name__)

HOME_HTML = f"""
<html>
<head><title>Mass Report Bot</title></head>
<body style="text-align:center; font-family:Arial; background:#0f0f1a; color:#fff; padding-top:80px;">
<h1>🤖 Mass Report Bot is ALIVE ✅</h1>
<p>Telegram Channel Mass Reporting Bot</p>
<p>💎 Credits: <b>{OWNER_CREDIT}</b></p>
</body>
</html>
"""


@flask_app.route("/")
def home():
    return HOME_HTML


@flask_app.route("/healthz")
def healthz():
    return "ok", 200


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ---------------- REPORT REASONS ----------------
REASONS = {
    "spam": ("🚫 Spam", InputReportReasonSpam()),
    "violence": ("🔥 Violence", InputReportReasonViolence()),
    "porno": ("🔞 Pornography", InputReportReasonPornography()),
    "child": ("🧒 Child Abuse", InputReportReasonChildAbuse()),
    "copyright": ("©️ Copyright", InputReportReasonCopyright()),
    "fake": ("🎭 Fake / Impersonation", InputReportReasonFake()),
    "other": ("📝 Other", InputReportReasonOther()),
}

REPORT_COOLDOWN = 60  # seconds per user

# Commands handled in group=0 — used by the admin state catcher to skip them
KNOWN_COMMANDS = {
    "/start", "/help", "/about", "/report", "/panel", "/stats",
    "/broadcast", "/addsession", "/delsession", "/ban", "/unban", "/cancel",
}

# ---------------- STATE ----------------
pending_reports = {}   # user_id -> {"target": str, "title": str}
pending_admin = {}     # ADMIN_ID -> {"action": "broadcast" | "addsession"}
user_cooldowns = {}    # user_id -> last report timestamp
commands_set = False


# ---------------- HELPERS ----------------
def parse_target(raw: str) -> str:
    t = raw.strip()
    if "t.me/" in t:
        t = t.split("t.me/")[-1]
    if t.startswith("@"):
        t = t[1:]
    if t.startswith("joinchat/"):
        t = "+" + t.split("joinchat/")[-1]
    return t


async def get_target_chat(c, target):
    if target.startswith("+"):
        return await c.join_chat(target)
    if target.lstrip("-").isdigit():
        return await c.get_chat(int(target))
    return await c.get_chat(target)


async def report_with_client(c, target: str, reason_key: str, is_bot: bool, retries: int = 2) -> bool:
    """
    Perform a report with a given client (bot or user session).
    - Bot accounts: only ReportSpam is reliable.
    - User sessions: try full Report with message IDs, fall back to ReportSpam.
    - FloodWait: retry up to `retries` times, then give up.
    """
    try:
        chat = await get_target_chat(c, target)
        peer = await c.resolve_peer(getattr(chat, "username", None) or chat.id)

        # --- Bot account path: only ReportSpam works reliably ---
        if is_bot:
            try:
                await c.invoke(ReportSpam(peer=peer))
                return True
            except Exception as e:
                print(f"[bot report error] {e}")
                return False

        # --- User session path: try full Report first ---
        reason = REASONS[reason_key][1]
        msg_ids = []
        try:
            async for msg in c.get_chat_history(chat.id, limit=10):
                msg_ids.append(msg.id)
        except Exception:
            msg_ids = []

        if msg_ids:
            await c.invoke(
                Report(peer=peer, id=msg_ids[:10], reason=reason, message="")
            )
        else:
            await c.invoke(ReportSpam(peer=peer))
        return True

    except FloodWait as e:
        if retries <= 0:
            print("[report] FloodWait retries exhausted.")
            return False
        print(f"[report] FloodWait {e.value}s — retrying ({retries} left).")
        await asyncio.sleep(e.value + 2)
        return await report_with_client(c, target, reason_key, is_bot, retries - 1)

    except Exception as e:
        print(f"[report error] {e}")
        return False


async def run_mass_report(bot, target, title, reason_key):
    started = time.time()
    success = 0
    failed = 0
    accounts = 0

    # 1) Bot account (ReportSpam only)
    accounts += 1
    if await report_with_client(bot, target, reason_key, is_bot=True):
        success += 1
    else:
        failed += 1

    # 2) User sessions
    sessions = db.get_sessions()
    for i, ss in enumerate(sessions):
        uc = None
        try:
            uc = Client(
                f"rep_{i}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=ss,
                in_memory=True,
            )
            await uc.start()
            accounts += 1
            if await report_with_client(uc, target, reason_key, is_bot=False):
                success += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"[session error] {e}")
        finally:
            if uc:
                try:
                    await uc.stop()
                except Exception:
                    pass
        await asyncio.sleep(1.5)

    took = round(time.time() - started, 1)

    text = (
        f"🎯 <b>Mass Report Finished</b>\n\n"
        f"📡 Target: <b>{title}</b>\n"
        f"📋 Reason: {REASONS[reason_key][0]}\n\n"
        f"🤖 Accounts Used: <b>{accounts}</b>\n"
        f"✅ Successful Reports: <b>{success}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"⏱ Time: <b>{took}s</b>\n\n"
        f"💎 Credits: <b>{OWNER_CREDIT}</b>"
    )
    return text, success


# ---------------- UI TEXT / KEYBOARDS ----------------
HELP_TEXT = (
    "📖 <b>How to use the Mass Report Bot</b>\n\n"
    "1️⃣ Send <code>/report @channelusername</code>\n"
    "   or <code>/report https://t.me/channelname</code>\n"
    "   or <code>/report +invite_hash</code>\n\n"
    "2️⃣ Choose a <b>report reason</b> from the buttons.\n\n"
    "3️⃣ The bot will mass-report using the bot account "
    "and all configured user sessions.\n\n"
    "⏳ <b>Cooldown:</b> 60s between reports per user.\n\n"
    f"💎 Credits: <b>{OWNER_CREDIT}</b>"
)


def about_text():
    return (
        f"💎 <b>{OWNER_CREDIT}</b>\n\n"
        "🤖 <b>Mass Report Bot</b>\n"
        "A Telegram channel mass-reporting tool.\n"
        "Built with Pyrogram.\n"
        "Storage: MongoDB."
    )


def stats_text():
    return (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Users: <b>{db.total_users()}</b>\n"
        f"🔗 Sessions: <b>{db.total_sessions()}</b>\n"
        f"🚨 Report Jobs: <b>{db.total_reports()}</b>\n"
        f"🎯 Total Reports Sent: <b>{db.total_report_count()}</b>"
    )


def panel_kb():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Stats", callback_data="adm_stats"),
                InlineKeyboardButton("👥 Users", callback_data="adm_users"),
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="adm_bcast"),
                InlineKeyboardButton("🔗 Sessions", callback_data="adm_sessions"),
            ],
            [
                InlineKeyboardButton("💎 About", callback_data="adm_about"),
                InlineKeyboardButton("❌ Close", callback_data="adm_close"),
            ],
        ]
    )


# ---------------- COMMANDS ----------------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    global commands_set
    if not commands_set:
        try:
            await client.set_bot_commands(
                [
                    BotCommand("start", "Start the bot"),
                    BotCommand("report", "Mass report a channel"),
                    BotCommand("help", "How to use"),
                    BotCommand("about", "About this bot"),
                ]
            )
        except Exception:
            pass
        commands_set = True

    user = message.from_user
    db.add_user(user.id, user.first_name or "User")

    if db.is_banned(user.id):
        return await message.reply("🚫 You are banned from using this bot.")

    text = (
        f"👋 <b>Hello {user.mention}!</b>\n\n"
        f"🤖 I am a <b>Mass Reporting Bot</b>.\n"
        f"⚡ I can mass report any Telegram channel using multiple accounts.\n\n"
        f"🎯 <b>How to use:</b>\n"
        f"➡️ /report @channelusername\n"
        f"➡️ Choose a report reason\n"
        f"➡️ Done! Mass report will start.\n\n"
        f"💎 Credits: <b>{OWNER_CREDIT}</b>"
    )
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎯 Report Now", callback_data="go_report"),
                InlineKeyboardButton("ℹ️ Help", callback_data="help_info"),
            ],
            [InlineKeyboardButton("💎 Credits", callback_data="credits_info")],
        ]
    )
    await message.reply(text, reply_markup=buttons)


@app.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message: Message):
    await message.reply(HELP_TEXT)


@app.on_message(filters.command("about") & filters.private)
async def about_cmd(client, message: Message):
    await message.reply(about_text())


@app.on_message(filters.command("report") & filters.private)
async def report_cmd(client, message: Message):
    user = message.from_user
    db.add_user(user.id, user.first_name or "User")

    if db.is_banned(user.id):
        return await message.reply("🚫 You are banned.")

    last = user_cooldowns.get(user.id, 0)
    if time.time() - last < REPORT_COOLDOWN:
        wait = int(REPORT_COOLDOWN - (time.time() - last))
        return await message.reply(f"⏳ Cooldown! Try again in {wait}s.")

    if len(message.command) < 2:
        return await message.reply(
            "❌ Usage: <code>/report @channelusername</code>\n"
            "or send channel link: <code>/report https://t.me/channelname</code>"
        )

    target = parse_target(" ".join(message.command[1:]))
    if not target:
        return await message.reply("❌ Invalid target.")

    if target.startswith("+"):
        title = "Invite-Link Channel"
    else:
        try:
            chat = await get_target_chat(client, target)
            title = chat.title or getattr(chat, "first_name", None) or target
        except Exception as e:
            return await message.reply(
                f"❌ Invalid channel or bot can't access it.\n<code>{e}</code>"
            )

    pending_reports[user.id] = {"target": target, "title": title}

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(name, callback_data=f"rpt_{key}")]
            for key, (name, _) in REASONS.items()
        ]
        + [[InlineKeyboardButton("❌ Cancel", callback_data="rpt_cancel")]]
    )
    await message.reply(
        f"🎯 Target: <b>{title}</b>\n\n👇 <b>Choose a report reason:</b>",
        reply_markup=kb,
    )


# ---------------- CALLBACKS ----------------
@app.on_callback_query()
async def cb_handler(client, cq: CallbackQuery):
    data = cq.data or ""
    uid = cq.from_user.id

    if data == "go_report":
        await cq.answer()
        return await cq.message.reply(
            "🎯 Send: <code>/report @channelusername</code>"
        )

    if data == "help_info":
        await cq.answer()
        return await cq.message.reply(HELP_TEXT)

    if data == "credits_info":
        await cq.answer()
        return await cq.message.reply(
            f"💎 This bot was built with credits to <b>{OWNER_CREDIT}</b>."
        )

    # ----- admin panel -----
    if data.startswith("adm_"):
        if uid != ADMIN_ID:
            return await cq.answer("🔐 Admins only!", show_alert=True)

        if data == "adm_stats":
            await cq.answer()
            return await cq.message.edit_text(stats_text(), reply_markup=panel_kb())

        if data == "adm_bcast":
            await cq.answer()
            pending_admin[ADMIN_ID] = {"action": "broadcast"}
            return await cq.message.reply(
                "📢 Send me the message to broadcast (text/photo/video).\n"
                "Send /cancel to abort."
            )

        if data == "adm_sessions":
            await cq.answer()
            sessions = db.get_sessions()
            lines = [
                f"{i}. <code>{s[:15]}...{s[-10:]}</code>"
                for i, s in enumerate(sessions, 1)
            ]
            text = (
                f"🔗 <b>User Sessions ({len(sessions)}):</b>\n\n"
                + ("\n".join(lines) or "No sessions yet. Use /addsession")
            )
            return await cq.message.edit_text(text, reply_markup=panel_kb())

        if data == "adm_users":
            await cq.answer()
            users = db.get_users()
            text = (
                f"👥 Total Users: <b>{len(users)}</b>\n\n"
                + "\n".join(str(u) for u in users[:50])
            )
            return await cq.message.edit_text(text, reply_markup=panel_kb())

        if data == "adm_about":
            await cq.answer()
            return await cq.message.edit_text(about_text(), reply_markup=panel_kb())

        if data == "adm_close":
            await cq.answer()
            return await cq.message.delete()

    # ----- report reasons -----
    if data == "rpt_cancel":
        pending_reports.pop(uid, None)
        await cq.answer("Cancelled")
        return await cq.message.edit_text("❌ Report cancelled.")

    if data.startswith("rpt_"):
        info = pending_reports.pop(uid, None)
        if not info:
            return await cq.answer(
                "⚠️ Session expired. Send /report again.", show_alert=True
            )

        reason_key = data[4:]
        if reason_key not in REASONS:
            reason_key = "spam"

        await cq.answer("🚀 Reporting started!")
        await cq.message.edit_text(
            f"⏳ <b>Mass reporting in progress...</b>\n"
            f"📡 Target: <b>{info['title']}</b>\n"
            f"📋 Reason: {REASONS[reason_key][0]}"
        )

        summary, success = await run_mass_report(
            client, info["target"], info["title"], reason_key
        )
        db.add_report(info["title"], success, uid)

        try:
            await cq.message.edit_text(summary)
        except Exception:
            await cq.message.reply(summary)

        try:
            await client.send_message(
                ADMIN_ID,
                f"🚨 <b>New Mass Report</b>\n"
                f"👤 By: {cq.from_user.mention} (<code>{uid}</code>)\n"
                f"📡 Target: <b>{info['title']}</b>\n"
                f"✅ Reports: <b>{success}</b>",
            )
        except Exception:
            pass

        user_cooldowns[uid] = time.time()
        return


# ---------------- ADMIN COMMANDS ----------------
@app.on_message(filters.command("panel") & filters.private & filters.user(ADMIN_ID))
async def panel_cmd(client, message: Message):
    await message.reply("🛡 <b>Admin Control Panel</b>", reply_markup=panel_kb())


@app.on_message(filters.command("stats") & filters.private & filters.user(ADMIN_ID))
async def stats_cmd(client, message: Message):
    await message.reply(stats_text())


@app.on_message(filters.command("broadcast") & filters.private & filters.user(ADMIN_ID))
async def broadcast_cmd(client, message: Message):
    pending_admin[ADMIN_ID] = {"action": "broadcast"}
    await message.reply("📢 Send the message to broadcast now (or /cancel).")


@app.on_message(filters.command("addsession") & filters.private & filters.user(ADMIN_ID))
async def addsession_cmd(client, message: Message):
    if len(message.command) > 1:
        ss = " ".join(message.command[1:]).strip()
        added = db.add_session(ss)
        if added:
            return await message.reply(
                f"✅ Session added! Total: {db.total_sessions()}"
            )
        return await message.reply(
            f"ℹ️ Session already exists. Total: {db.total_sessions()}"
        )

    pending_admin[ADMIN_ID] = {"action": "addsession"}
    await message.reply(
        "🔗 Send the <b>Pyrogram session string</b> to add (or /cancel)."
    )


@app.on_message(filters.command("delsession") & filters.private & filters.user(ADMIN_ID))
async def delsession_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: <code>/delsession &lt;index&gt;</code>")
    try:
        idx = int(message.command[1]) - 1
        sessions = db.get_sessions()
        if 0 <= idx < len(sessions):
            ok = db.del_session(sessions[idx])
            if ok:
                return await message.reply(f"🗑 Deleted session #{idx + 1}.")
            return await message.reply("⚠️ Session not found in database.")
        return await message.reply("❌ Invalid index.")
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("ban") & filters.private & filters.user(ADMIN_ID))
async def ban_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: <code>/ban &lt;user_id&gt;</code>")
    try:
        uid = int(message.command[1])
        db.ban_user(uid)
        return await message.reply(f"🚫 Banned <code>{uid}</code>.")
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("unban") & filters.private & filters.user(ADMIN_ID))
async def unban_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: <code>/unban &lt;user_id&gt;</code>")
    try:
        uid = int(message.command[1])
        db.unban_user(uid)
        return await message.reply(f"✅ Unbanned <code>{uid}</code>.")
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("cancel") & filters.private & filters.user(ADMIN_ID))
async def cancel_cmd(client, message: Message):
    pending_admin.pop(ADMIN_ID, None)
    await message.reply("✅ Cancelled pending action.")


# ---------------- ADMIN STATE CATCHER ----------------
# group=1 runs AFTER command handlers (group=0), so commands still work.
@app.on_message(filters.private & filters.user(ADMIN_ID), group=1)
async def admin_state_catcher(client, message: Message):
    state = pending_admin.get(ADMIN_ID)
    if not state:
        return

    # Skip only known commands — allows session strings that start with "/"
    if message.text and message.text.startswith("/"):
        cmd = message.text.split(maxsplit=1)[0].lower()
        if cmd in KNOWN_COMMANDS:
            return

    # Only accept broadcastable message types
    if not (
        message.text
       or message.photo
        or message.video
        or message.document
        or message.animation
    ):
        return

    action = state.get("action")
    pending_admin.pop(ADMIN_ID, None)

    if action == "broadcast":
        users = db.get_users()
        sent = 0
        failed = 0
        await message.reply(f"📢 Broadcasting to {len(users)} users...")
        for uid in users:
            try:
                await message.copy(uid)
                sent += 1
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                try:
                    await message.copy(uid)
                    sent += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
        return await message.reply(
            f"✅ Broadcast done.\n\n✅ Sent: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>"
        )

    if action == "addsession":
        ss = (message.text or "").strip()
        if not ss:
            return await message.reply("❌ Session string required.")
        added = db.add_session(ss)
        if added:
            return await message.reply(
                f"✅ Session added! Total: {db.total_sessions()}"
            )
        return await message.reply(
            f"ℹ️ Session already exists. Total: {db.total_sessions()}"
        )


# ---------------- MAIN ----------------
def start_flask():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()


async def main():
    # ⚠️ Pyrogram's Client.run() already calls start()/stop() internally.
    # Do NOT call app.start() / app.stop() here — it will raise ConnectionError.
    start_flask()
    print("🤖 Bot started successfully.")
    await idle()


if __name__ == "__main__":
    app.run(main())