import os
import json
import random
import logging
import time # Needed for synchronization logic
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, JobQueue
)

# ================== CONFIG ==================
# NOTE: Replace with your actual bot token and SUDO user ID
TOKEN = "8357436600:AAEqoZvNjoDvy5H1gBet_aPOyfBarDDcr4g"
DATA_FILE = "anime_game_data.json"
# CHALLENGE_INTERVAL is loaded from GameData if present, otherwise defaults here.
# It is stored and updated globally via GameData.
SUDO_ID = 8442334913
# ============================================

CHARACTERS = [
    "Asuna", "Rem", "Emilia", "Nezuko", "Hinata",
    "Sakura", "Mikasa", "Zero Two", "Megumin", "Kurumi",
    "Rias", "Akeno", "Toga", "Yor", "Makima", "Nico", "Robin",
    "Boa", "Tsunade", "Ino", "Eris", "Yuno", "Milly"
]

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================== GAME DATA MANAGEMENT ==================
class GameData:
    """Manages loading and saving of bot data, including the global interval."""
    def __init__(self):
        self.user_scores = {}
        self.current_challenges = {}
        self.active_groups = set()
        # Global variable for drop interval, defaults to 10 minutes (600s)
        self.challenge_interval = 1
        self.load()

    def load(self):
        """Loads data from the JSON file if it exists."""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                    self.user_scores = data.get("user_scores", {})
                    self.current_challenges = data.get("current_challenges", {})
                    self.active_groups = set(str(g) for g in data.get("active_groups", []))
                    # Load the interval, using the default if not found
                    self.challenge_interval = data.get("challenge_interval", 600)
                logger.info("Game data loaded successfully.")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading data: {e}. Starting with empty data.")
        else:
            logger.info("Data file not found. Starting with empty data.")

    def save(self):
        """Saves current data to the JSON file."""
        with open(DATA_FILE, "w") as f:
            json.dump({
                "user_scores": self.user_scores,
                "current_challenges": self.current_challenges,
                "active_groups": list(self.active_groups),
                "challenge_interval": self.challenge_interval # Save the interval
            }, f, indent=4)

game_data = GameData()
# ==========================================================

# ================== JOB QUEUE HELPERS ==================

def remove_existing_jobs(job_queue: JobQueue, chat_id: int):
    """Removes the spawn job for a specific chat ID."""
    job_name = f"spawn_{chat_id}"
    current_jobs = job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
        logger.info(f"Removed old spawn job for group ID: {chat_id}")

def start_spawn_job(job_queue: JobQueue, chat_id: int):
    """
    Starts the repeating character spawn job, synchronized across all groups.
    Uses the currently loaded game_data.challenge_interval.
    """
    gid_str = str(chat_id)
    job_name = f"spawn_{gid_str}"
    
    # Check if the job is already running to prevent duplicates (important after init/settime)
    if job_queue.get_jobs_by_name(job_name):
        logger.info(f"Spawn job for group ID: {chat_id} is already running. Skipping start.")
        return

    interval = game_data.challenge_interval
    
    # --- Synchronization Logic ---
    current_time_sec = time.time()
    remainder = current_time_sec % interval
    time_until_next_drop = interval - remainder
    
    if time_until_next_drop < 1:
         time_until_next_drop += interval
    # --- End Synchronization Logic ---
    
    job_queue.run_repeating(
        spawn_character, 
        interval=interval,
        first=time_until_next_drop, # Use the calculated offset for alignment
        chat_id=chat_id, 
        name=job_name
    )
    logger.info(f"Started SYNCHRONIZED spawn job for group ID: {chat_id}. Interval: {interval}s. First drop in {time_until_next_drop:.2f}s.")


async def spawn_character(context: ContextTypes.DEFAULT_TYPE):
    """
    Schedules a new character to appear in a chat.
    If a character was missed, it is silently replaced by the new one.
    """
    gid = str(context.job.chat_id)
    chat_id_int = context.job.chat_id
    
    # Check for and silently replace any missed character
    if gid in game_data.current_challenges:
        previous_char = game_data.current_challenges.pop(gid)
        logger.info(f"Silently replacing un-caught character in group {gid}: {previous_char}")
        
    character = random.choice(CHARACTERS)
    logger.info(f"Spawning new character in group {gid}: {character}")
    
    await context.bot.send_message(
        chat_id=chat_id_int,
        text=f"A character has appeared so type fast vro fr coming in leadeboard...\n 🌹type: {character}"
    )

    # Update the challenge
    game_data.current_challenges[gid] = character
    game_data.save()


# ================== COMMAND HANDLERS ==================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    if chat_type == "private":
        text = "I'm anime type bot. Add me in a group and type the characters' names"
        button = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("Add me to a group", url=f"https://t.me/{context.bot.username}?startgroup=true")
        )
        await update.message.reply_text(text, reply_markup=button)
    else:
        await update.message.reply_text("Me jinda hu vro")
        gid_str = str(chat_id)
        
        if gid_str not in game_data.active_groups:
            game_data.active_groups.add(gid_str)
            game_data.save()
            logger.info(f"Group {gid_str} added and saved.")
        
        start_spawn_job(context.job_queue, chat_id)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the top 10 players in plain text."""
    if not game_data.user_scores:
        await update.message.reply_text("No players yet.")
        return
        
    top = sorted(game_data.user_scores.values(), key=lambda x: x["score"], reverse=True)[:10]
    
    msg = "leadrboard\n"
    msg += "-------------------------\n"
    
    for i, data in enumerate(top, 1):
        msg += f"{i}. {data['username']} - {data['score']} points\n"
        
    await update.message.reply_text(msg)

# ================== MESSAGE HANDLER ==================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all text messages to check for character catch."""
    if update.effective_chat.type == "private":
        return
        
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    text = update.message.text.strip()

    if gid in game_data.current_challenges:
        correct_char = game_data.current_challenges[gid]
        
        if text.lower() == correct_char.lower():
            del game_data.current_challenges[gid]
            name = update.effective_user.first_name
            
            user = game_data.user_scores.setdefault(uid, {"username": name, "score": 0})
            user["score"] += 1
            user["username"] = name
            game_data.save()
            
            await context.bot.send_message(
                chat_id=int(gid),
                text=f"{name} typed it first! +1 point (Total: {user['score']})"
            )

# ================== SUDO COMMANDS ==================

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SUDO command to add a new character to the list."""
    if update.effective_user.id != SUDO_ID:
        await update.message.reply_text("You are not allowed to use this command.")
        return
        
    if not context.args:
        await update.message.reply_text("Usage: /upload Character Name")
        return
        
    char_name = " ".join(context.args).strip()
    
    if char_name.lower() in [c.lower() for c in CHARACTERS]:
        await update.message.reply_text(f"'{char_name}' (or a case-variant) already exists.")
        return
        
    CHARACTERS.append(char_name)
    await update.message.reply_text(f"Character '{char_name}' uploaded successfully!")
    logger.info(f"SUDO added new character: {char_name}")


async def wdrop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SUDO command to immediately drop a character in the current chat."""
    if update.effective_user.id != SUDO_ID:
        await update.message.reply_text("You are not allowed to use this command.")
        return

    gid = str(update.effective_chat.id)
    chat_id_int = update.effective_chat.id
    character = random.choice(CHARACTERS)
    
    game_data.current_challenges[gid] = character
    game_data.save()
    
    await context.bot.send_message(
        chat_id=chat_id_int, 
        text=f"A character has been dropped\n 🌹type: {character}"
    )
    logger.info(f"SUDO forced character drop: {character} in group {gid}")


async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SUDO command to globally set the drop interval and restart jobs."""
    if update.effective_user.id != SUDO_ID:
        await update.message.reply_text("You are not allowed to use this command.")
        return

    if not context.args or not context.args[0].isdigit():
        current = game_data.challenge_interval
        await update.message.reply_text(f"Usage: /settime [seconds]. Current interval is {current} seconds.")
        return

    try:
        new_interval = int(context.args[0])
        if new_interval < 5:
            await update.message.reply_text("Interval must be at least 5 seconds.")
            return

        old_interval = game_data.challenge_interval
        game_data.challenge_interval = new_interval
        game_data.save()
        
        # Restart all existing synchronized jobs with the new interval
        for gid_str in game_data.active_groups:
            chat_id = int(gid_str)
            remove_existing_jobs(context.job_queue, chat_id)
            start_spawn_job(context.job_queue, chat_id)

        await update.message.reply_text(f"Global drop interval updated from {old_interval}s to {new_interval}s.\nAll active groups have been synchronized to the new schedule.")
        logger.info(f"SUDO changed interval from {old_interval}s to {new_interval}s.")

    except ValueError:
        await update.message.reply_text("Invalid value. Please provide an integer in seconds.")


# ================== MAIN EXECUTION ==================

def init_jobs(app: ApplicationBuilder):
    """Initializes spawn jobs for all active groups upon bot startup, ensuring synchronization."""
    job_queue = app.job_queue
    logger.info(f"Attempting to initialize jobs for {len(game_data.active_groups)} active groups.")
    
    for gid_str in game_data.active_groups:
        try:
            chat_id = int(gid_str)
            # Use the synchronized job starter
            start_spawn_job(job_queue, chat_id)
        except ValueError:
            logger.error(f"Invalid group ID found in data: {gid_str}. Skipping.")


def main():
    """Starts the bot."""
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Initialize jobs using the synchronized logic
    init_jobs(app) 

    # --- Command Handlers ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    
    # SUDO commands
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("wdrop", wdrop))
    app.add_handler(CommandHandler("settime", settime_command)) # <<< NEW HANDLER
    
    # Message handler must come last
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot started and polling...")
    app.run_polling()
    # Note on Deployment: If running on a platform like Heroku or certain cloud functions, 
    # use a dedicated webhooks setup instead of run_polling(). 
    # For a simple VPS, run_polling() should be fine.

if __name__ == "__main__":
    main()
