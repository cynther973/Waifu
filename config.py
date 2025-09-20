import os

# --- Bot Configuration ---
# Get the bot token from an environment variable for security
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Get the sudo user ID from an environment variable
try:
    SUDO_ID = int(os.getenv("SUDO_ID"))
except (ValueError, TypeError):
    # Set a default value or handle the error
    SUDO_ID = None

# --- Other Configurations ---
DATABASE_FILE = "bot_data.db"

# Drop rates and cooldowns
MESSAGES_UNTIL_DROP = 100
DAILY_COOLDOWN = 24 * 60 * 60
SHOP_COOLDOWN = 24 * 60 * 60
SHOP_LIMIT = 3
DIG_COOLDOWN = 10 * 60
HAREM_PAGE_SIZE = 10
MIN_GROUP_MEMBERS = 15

# Global storage for in-memory data (will be lost on restart)
SPAWNED_CHARACTERS = {}
USER_MESSAGE_OWNERSHIP = {}
MESSAGE_COUNTERS = {}
