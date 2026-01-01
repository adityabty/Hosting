#!/usr/bin/env python3
import os
import shutil
import subprocess
from datetime import datetime
from pymongo import MongoClient

import logging
logging.basicConfig(level=logging.INFO)

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    JobQueue
)

print("🚀 Bot starting... please wait")

# =========================
# CONFIG
# =========================
BOT_TOKEN = "YOUR_PANEL_BOT_TOKEN"
ADMIN_IDS = [123456789]
LOGGER_GROUP = -1001234567890
MONGO = "YOUR_MONGO_URI"
START_IMAGE = "https://i.ibb.co/1JTzMMqh/x.jpg"

BASE_MUSIC_REPO = "/root/music_base"
BASE_CHAT_REPO = "/root/chat_base"
WORKDIR = "/root/clients"

# =========================
# DATABASE
# =========================
mongo = MongoClient(MONGO)
db = mongo["hosting_panel"]
users = db["users"]
bots = db["bots"]


# =========================
# HELPERS
# =========================
def ensure_user(uid):
    if not users.find_one({"_id": uid}):
        users.insert_one({"_id": uid, "credits": 0})


def cut_credit(uid, amount):
    u = users.find_one({"_id": uid})
    if not u or u["credits"] < amount:
        return False
    users.update_one({"_id": uid}, {"$inc": {"credits": -amount}})
    return True


async def send_log(app, text):
    try:
        await app.bot.send_message(LOGGER_GROUP, text)
    except Exception:
        pass


def stop_bot(bot_id):
    bot = bots.find_one({"_id": bot_id})
    if not bot:
        return

    try:
        subprocess.run(["pkill", "-f", bot["run_file"]])
    except Exception:
        pass

    bots.update_one({"_id": bot_id}, {"$set": {"status": "stopped"}})


# =========================
# DEPLOY BOT
# =========================
def deploy_bot(uid, bot_type, env_data, bot_name):
    user_dir = os.path.join(WORKDIR, str(uid))
    os.makedirs(user_dir, exist_ok=True)

    repo = BASE_MUSIC_REPO if bot_type == "music" else BASE_CHAT_REPO
    bot_dir = os.path.join(user_dir, bot_name)

    if os.path.exists(bot_dir):
        shutil.rmtree(bot_dir)

    shutil.copytree(repo, bot_dir)

    # .env file write
    with open(os.path.join(bot_dir, ".env"), "w") as f:
        for k, v in env_data.items():
            f.write(f"{k}={v}\n")

    # venv + deps
    venv = os.path.join(bot_dir, "venv")
    subprocess.run(["python3", "-m", "venv", venv])
    subprocess.run([f"{venv}/bin/pip", "install", "--upgrade", "pip"])
    subprocess.run([
        f"{venv}/bin/pip", "install",
        "-r", os.path.join(bot_dir, "requirements.txt")
    ])

    # start script
    start_sh = os.path.join(bot_dir, "start.sh")
    with open(start_sh, "w") as f:
        f.write(f"""#!/bin/bash
cd "{bot_dir}"
source venv/bin/activate
python3 -m {"XMUSIC" if bot_type=="music" else "main"}
""")
    os.chmod(start_sh, 0o755)

    subprocess.Popen(["bash", start_sh])

    bots.insert_one({
        "_id": f"{uid}_{bot_name}",
        "uid": uid,
        "name": bot_name,
        "type": bot_type,
        "run_file": start_sh,
        "status": "running",
        "created": datetime.now()
    })


# =========================
# UI MENUS
# =========================
def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Music Bot Hosting", callback_data="music_host"),
            InlineKeyboardButton("🤖 Chat Bot Hosting", callback_data="chat_host")
        ],
        [InlineKeyboardButton("🧾 My Bots", callback_data="my_bots")],
        [InlineKeyboardButton("💳 My Credits", callback_data="credits")],
        [InlineKeyboardButton("📦 Plans", callback_data="plans")],
        [InlineKeyboardButton("📘 How To Deploy", callback_data="how")]
    ])


PLANS = [
    ("₹49 — 150 Credits — 1 Bot", "plan_49"),
    ("₹99 — 300 Credits — 2 Bots", "plan_99"),
    ("₹450 — 1100 Credits — 5 Bots", "plan_450"),
    ("₹999 — 7000 Credits — Unlimited", "plan_999"),
]


def plans_ui():
    rows = [[InlineKeyboardButton(p[0], callback_data=p[1])] for p in PLANS]
    rows += [[InlineKeyboardButton("💬 Buy From Admin", url="https://t.me/adarshji4")]]
    return InlineKeyboardMarkup(rows)


def my_bots_ui(uid):
    rows = []

    for b in bots.find({"uid": uid}):
        status = "🟢" if b["status"] == "running" else "🔴"
        rows.append([
            InlineKeyboardButton(
                f"{status} {b['name']} ({b['type']})",
                callback_data="noop"
            )
        ])
        if b["status"] == "running":
            rows.append([
                InlineKeyboardButton(
                    "⛔ Stop Bot",
                    callback_data=f"stop:{b['_id']}"
                )
            ])

    if not rows:
        rows = [[InlineKeyboardButton("❌ No Bots Found", callback_data="noop")]]

    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="back_home")])
    return InlineKeyboardMarkup(rows)


# =========================
# START
# =========================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user.id)

    await update.message.reply_photo(
        photo=START_IMAGE,
        caption=(
            "👋 *Welcome to Infinity Era Hosting*\n\n"
            "⚡ Auto Bot Hosting Platform\n"
            "🎵 Music Bots | 🤖 Chat Bots\n"
            "💳 Credit Based Hosting"
        ),
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )


# =========================
# CALLBACKS
# =========================
async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    ensure_user(uid)

    data = q.data

    if data == "back_home":
        await q.message.edit_text("🏠 Main Menu", reply_markup=main_menu())

    elif data.startswith("stop:"):
        stop_bot(data.split(":", 1)[1])
        await q.answer("Bot Stopped")
        await q.message.edit_text("🧾 My Bots", reply_markup=my_bots_ui(uid))

    elif data == "my_bots":
        await q.message.edit_text("🧾 My Bots", reply_markup=my_bots_ui(uid))

    elif data == "credits":
        u = users.find_one({"_id": uid})
        await q.message.edit_text(
            f"💳 Your Credits: *{u['credits']}*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif data == "plans":
        await q.message.edit_text("📦 Available Plans", reply_markup=plans_ui())

    elif data == "how":
        await q.message.edit_text(
            "📘 How To Deploy\n\n"
            "1️⃣ Select Bot Type\n"
            "2️⃣ Enter Bot Token + IDs\n"
            "3️⃣ Wait… Deploying…\n"
            "4️⃣ Bot Ready 🎉\n\n"
            "⚠️ Credit finish → Auto Stop",
            reply_markup=main_menu()
        )

    elif data == "music_host":
        ctx.user_data.update(step="name", deploy_type="music")
        await q.message.reply_text("🎵 Send Bot Name:")

    elif data == "chat_host":
        ctx.user_data.update(step="name", deploy_type="chat")
        await q.message.reply_text("🤖 Send Bot Name:")


# =========================
# TEXT FLOW
# =========================
async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)

    step = ctx.user_data.get("step")

    if step == "name":
        ctx.user_data["bot_name"] = update.message.text
        ctx.user_data["step"] = "token"
        await update.message.reply_text("🔑 Send Bot Token")

    elif step == "token":
        ctx.user_data["token"] = update.message.text
        ctx.user_data["step"] = "owner"
        await update.message.reply_text("👤 Send Owner ID")

    elif step == "owner":
        ctx.user_data["owner"] = update.message.text
        ctx.user_data["step"] = "logger"
        await update.message.reply_text("📝 Send Logger ID")

    elif step == "logger":
        ctx.user_data["logger"] = update.message.text
        ctx.user_data["step"] = "string"
        await update.message.reply_text("💠 Send STRING SESSION (write none if not needed)")

    elif step == "string":
        string_val = "" if update.message.text.lower() == "none" else update.message.text

        env = {
            "BOT_TOKEN": ctx.user_data["token"],
            "OWNER_ID": ctx.user_data["owner"],
            "LOGGER_ID": ctx.user_data["logger"],
            "STRING_SESSION": string_val
        }

        if not cut_credit(uid, 1):
            await update.message.reply_text("❌ Not enough credits")
            ctx.user_data.clear()
            return

        deploy_bot(
            uid,
            ctx.user_data["deploy_type"],
            env,
            ctx.user_data["bot_name"]
        )

        await update.message.reply_text("🚀 Deploying… please wait\n\n🎉 Bot Ready!")

        await send_log(
            ctx.application,
            (
                f"🚀 BOT DEPLOYED\n\n"
                f"👤 User: {uid}\n"
                f"🤖 Bot: {ctx.user_data['bot_name']}\n"
                f"🧩 Type: {ctx.user_data['deploy_type']}"
            )
        )

        ctx.user_data.clear()


# =========================
# ADMIN: ADD CREDITS
# =========================
async def addcredit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    try:
            uid = int(ctx.args[0])
            amt = float(ctx.args[1])
            users.update_one({"_id": uid}, {"$inc": {"credits": amt}}, upsert=True)
            await update.message.reply_text("✔ Credit Added")
    except Exception:
            await update.message.reply_text("Usage: /addcredit user_id amount")


# =========================
# CREDIT JOB (HOURLY)
# =========================
async def credit_job(context):
    app = context.application

    for bot in bots.find({"status": "running"}):
        cost = 1 if bot["type"] == "music" else 0.5

        if not cut_credit(bot["uid"], cost):
            stop_bot(bot["_id"])
            await send_log(
                app,
                (
                    f"⛔ BOT STOPPED — Credits Finished\n\n"
                    f"👤 User: {bot['uid']}\n"
                    f"🤖 Bot: {bot['name']}"
                )
            )


# =========================
# RUN APP
# =========================
app = ApplicationBuilder().token(BOT_TOKEN).build()

# guarantee job queue exists
if app.job_queue is None:
    app.job_queue = JobQueue()
    app.job_queue.set_application(app)

print("🤖 Bot is now running (Polling Started)")

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addcredit", addcredit))
app.add_handler(CallbackQueryHandler(callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# hourly credit deduction
app.job_queue.run_repeating(credit_job, interval=3600, first=10)

app.run_polling()
