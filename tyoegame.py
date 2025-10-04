import os
import json
import random
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters, JobQueue
)

# ================== CONFIG ==================
TOKEN = "8357436600:AAEqoZvNjoDvy5H1gBet_aPOyfBarDDcr4g"
DATA_FILE = "anime_game_data.json"
CHALLENGE_INTERVAL = 600 # 10 minutes
SUDO_ID = 8442334913
# ============================================

CHARACTERS = [
    "Asuna", "Rem", "Emilia", "Nezuko", "Hinata",
    "Sakura", "Mikasa", "Zero Two", "Megumin", "Kurumi",
    "Rias", "Akeno", "Toga", "Yor", "Makima", "Nico", "Robin",
    "Boa", "Tsunade", "Ino", "Eris", "Yuno", "Milly"
]

RARITIES = [
    ("Premium", "💠"),
    ("Rare", "🟢"),
    ("Epic", "🟣"),
    ("Legendary", "🟡"),
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== GAME DATA ==================
class GameData:
    def __init__(self):
        self.user_scores = {}
        self.current_challenges = {}
        self.active_groups = set()
        self.load()

    def load(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                self.user_scores = data.get("user_scores", {})
                self.current_challenges = data.get("current_challenges", {})
                self.active_groups = set(data.get("active_groups", []))

    def save(self):
        with open(DATA_FILE, "w") as f:
            json.dump({
                "user_scores": self.user_scores,
                "current_challenges": self.current_challenges,
                "active_groups": list(self.active_groups)
            }, f)

game_data = GameData()

# ================== SPAWN LOGIC ==================
async def spawn_character(context: ContextTypes.DEFAULT_TYPE):
    gid = str(context.job.chat_id)
    if gid in game_data.current_challenges:
        # Previous character not caught, spawn new one
        character = random.choice(CHARACTERS)
        game_data.current_challenges[gid] = character
        game_data.save()
        await context.bot.send_message(chat_id=int(gid),
                                       text=f"A character has appeared so type fast vro fr coming in leadeboard...⌨️⌨️type: {character} ")
    else:
        character = random.choice(CHARACTERS)
        game_data.current_challenges[gid] = character
        game_data.save()
        await context.bot.send_message(chat_id=int(gid),
                                       text=f"A character has appeared: {character}")

# ================== COMMANDS ==================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type == "private":
        text = "I'm anime type bot. Add me in a group and type the characters' names"
        button = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("Add me to a group", url=f"https://t.me/{context.bot.username}?startgroup=true")
        )
        await update.message.reply_text(text, reply_markup=button)
    else:
        await update.message.reply_text("Me jinda hu vro 🌚")
        gid_str = str(update.effective_chat.id)
        game_data.active_groups.add(gid_str)
        game_data.save()
        # Start auto spawn for this group
        context.job_queue.run_repeating(spawn_character, interval=CHALLENGE_INTERVAL,
                                        first=1, chat_id=update.effective_chat.id, name=f"spawn_{gid_str}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    text = update.message.text.strip().lower()

    if gid in game_data.current_challenges:
        correct = game_data.current_challenges[gid].lower()
        if text == correct:
            del game_data.current_challenges[gid]
            name = update.effective_user.first_name
            user = game_data.user_scores.setdefault(uid, {"username": name, "score": 0})
            user["score"] += 1
            game_data.save()
            await context.bot.send_message(chat_id=int(gid),
                                           text=f"{name} typed it first! +1 point (Total: {user['score']})")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not game_data.user_scores:
        await update.message.reply_text("No players yet.")
        return
    top = sorted(game_data.user_scores.items(), key=lambda x: x[1]["score"], reverse=True)[:10]
    msg = "Top Players:\n"
    for i, (uid, data) in enumerate(top, 1):
        msg += f"{i}. {data['username']} – {data['score']} points\n"
    await update.message.reply_text(msg)

# ================== SUDO COMMAND ==================
async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUDO_ID:
        await update.message.reply_text("You are not allowed to use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /upload [character name]")
        return
    char_name = " ".join(context.args).strip()
    if char_name in CHARACTERS:
        await update.message.reply_text(f"'{char_name}' already exists.")
        return
    CHARACTERS.append(char_name)
    await update.message.reply_text(f"Character '{char_name}' uploaded successfully!")

async def wdrop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUDO_ID:
        await update.message.reply_text("You are not allowed to use this command.")
        return

    gid = str(update.effective_chat.id)
    character = random.choice(CHARACTERS)
    game_data.current_challenges[gid] = character
    game_data.save()
    await context.bot.send_message(chat_id=int(gid), text=f"A character has been dropped: {character}")

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("wdrop", wdrop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()