import os
import random
import sqlite3
import asyncio
import logging
import time
import psutil
import string
from collections import defaultdict
import unicodedata

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaVideo, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

# --- Configuration ---
TOKEN = "7636797595:AAHKEYl_D1Zl8gZeAEIsHgukJWEk1_uaJVU"  # ⚠️ REPLACE WITH YOUR ACTUAL BOT TOKEN
SUDO_ID = 8150699034
DATABASE_FILE = "bot_data.db"
DAILY_COOLDOWN = 24 * 60 * 60
SHOP_COOLDOWN = 24 * 60 * 60
SHOP_LIMIT = 3
DIG_COOLDOWN = 10 * 60
HAREM_PAGE_SIZE = 10
MIN_GROUP_MEMBERS = 15

# Global storage for spawned characters (stores chat_id: character_name)
spawned_characters = {}
# Global storage to track inline button ownership
user_message_ownership = {}

# Global storage for message counts and drop time
messages_until_drop = 100
message_counters = defaultdict(int)

# --- Utility Functions ---

def normalize_name_for_match(text):
    """Normalizes a string for case-insensitive matching."""
    if not isinstance(text, str):
        return ""
    # Use casefold() for case-insensitive matching
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8').casefold().strip()

def get_user_display_name(user):
    """Returns the user's full display name (first + last name if available)."""
    name = user.first_name
    if user.last_name:
        name += f" {user.last_name}"
    return name

def apply_font(text):
    """Adds a special font to a given string."""
    font_map = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ',
        'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
        's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ'
    }
    return ''.join(font_map.get(char.lower(), char) for char in text)

def generate_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def is_sudo(user_id):
    return user_id == SUDO_ID

def get_db_connection():
    return sqlite3.connect(DATABASE_FILE)

# --- Database Setup and Migration ---
def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rarities (
            name TEXT PRIMARY KEY,
            emoji TEXT NOT NULL,
            spawn_weight INTEGER NOT NULL,
            shop_price INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS characters (
            character_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            file_id TEXT NOT NULL,
            rarity TEXT NOT NULL,
            is_video INTEGER DEFAULT 0,
            uploaded_by TEXT,
            anime_name TEXT
        )
    ''')

    # MODIFICATION: Added last_updated and group_id columns
    # MODIFICATION: Changed username to store the full display name without normalization
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaderboard (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            score INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            last_daily_claim INTEGER DEFAULT 0,
            last_daily_bonus INTEGER DEFAULT 0,
            last_dig_claim INTEGER DEFAULT 0,
            fav_char_id INTEGER DEFAULT NULL,
            shop_uses INTEGER DEFAULT 0,
            last_shop_reset INTEGER DEFAULT 0,
            last_slot_claim INTEGER DEFAULT 0,
            last_updated INTEGER DEFAULT 0,
            group_id INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_harem (
            user_id INTEGER,
            character_id INTEGER,
            grab_count INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, character_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcast_targets (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            last_seen INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_settings (
            setting_name TEXT PRIMARY KEY,
            setting_value TEXT
        )
    ''')

    # New tables for redeem codes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_redeem_codes (
            code TEXT PRIMARY KEY,
            character_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coin_redeem_codes (
            code TEXT PRIMARY KEY,
            coins INTEGER NOT NULL,
            quantity INTEGER NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS claimed_codes (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    ''')

    # New table for limited sudo users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS limited_sudo (
            user_id INTEGER PRIMARY KEY
        )
    ''')

    # NEW TABLE: To store group information
    # MODIFICATION: Changed group_name to store the full, non-normalized name
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY,
            group_name TEXT NOT NULL
        )
    ''')

    # Add new columns if they don't exist
    def add_column_if_not_exists(table, column, definition):
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                pass
            else:
                logging.error(f"Error adding column {column} to table {table}: {e}")

    add_column_if_not_exists('rarities', 'shop_price', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('leaderboard', 'fav_char_id', 'INTEGER DEFAULT NULL')
    add_column_if_not_exists('user_harem', 'grab_count', 'INTEGER DEFAULT 1')
    add_column_if_not_exists('leaderboard', 'shop_uses', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('leaderboard', 'last_shop_reset', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('leaderboard', 'last_slot_claim', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('leaderboard', 'last_updated', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('leaderboard', 'group_id', 'INTEGER DEFAULT 0')

    conn.commit()
    conn.close()

# --- Command Handlers ---
async def check_group_members(context: CallbackContext, chat_id: int):
    """
    Checks if a group has a minimum number of members and leaves if it doesn't.
    Excludes the support group from this check.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name = 'support_group_link'")
    support_link = cursor.fetchone()
    conn.close()

    if support_link and str(chat_id) == support_link[0].split('/')[-1]:
        return True # Don't leave the support group

    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
        if member_count < MIN_GROUP_MEMBERS:
            await context.bot.send_message(
                chat_id=chat_id,
                text=apply_font(f"❌ This group has less than {MIN_GROUP_MEMBERS} members. Leaving.")
            )
            await context.bot.leave_chat(chat_id)
            return False
    except Forbidden:
        logging.info(f"Bot was removed from chat {chat_id} before it could check members.")
        return False
    except Exception as e:
        logging.error(f"Could not get member count for chat {chat_id}: {e}")
        return True # Assume it's okay to stay if we can't check
    return True

# /start command
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_group_members(context, update.effective_chat.id):
            return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO broadcast_targets (id, type) VALUES (?, ?)", 
            (user_id, 'user')
        )

        cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name = 'support_group_link'")
        support_link = cursor.fetchone()

        cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name = 'start_pic'")
        start_pic_file_id = cursor.fetchone()
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database error in start command: {e}")
        conn.rollback()
        await update.message.reply_text(apply_font("An internal error occurred."))
        return
    finally:
        conn.close()

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Me to Group", url=f"http://t.me/{context.bot.username}?startgroup=true")
        ],
        [
            InlineKeyboardButton("🔮 Developer", url=f"tg://user?id={SUDO_ID}")
        ]
    ]

    if support_link:
        keyboard[1].insert(0, InlineKeyboardButton("🌟 Support", url=support_link[0]))

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Fix: Separate font from markdown for the links
    welcome_message = (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━⧫\n"
        f"  ✦ {apply_font('Shota x Waifu Bot')} ✦\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━⧫\n"
        f"{apply_font('• I can help you find your waifu or husbando in your group chat.')}\n"
        f"{apply_font('• You can guess the character name using')} `/grab [name]` {apply_font('and add them to your collection.')}\n"
        f"{apply_font('• Use')} `/harem` {apply_font('to view your characters and')} `/leaderboard` {apply_font('to see the top collectors.')}\n"
        "\n"
        f"{apply_font('Tap on the buttons below for more info.')}"
    )

    if update.effective_chat.type == "private":
        try:
            if start_pic_file_id:
                await update.message.reply_photo(
                    photo=start_pic_file_id[0], 
                    caption=welcome_message,
                    reply_markup=reply_markup, 
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(apply_font("I'm alive"))

# /help command (now as a callback handler)
async def help_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    help_text = (
        f"✦ {apply_font('COMMANDS')} ✦\n\n"
        f"{apply_font('User Commands:')}\n"
        f"  `•` /start - {apply_font('Start the bot')}\n"
        f"  `•` /leaderboard - {apply_font('See top grabbers')}\n"
        f"  `•` /topcoins - {apply_font('See top coin hoarders')}\n"
        f"  `•` /harem - {apply_font('View your collection')}\n"
        f"  `•` /fav - {apply_font('Set a favorite character')}\n"
        f"  `•` /sclaim - {apply_font('Get a daily character')}\n"
        f"  `•` /bonus - {apply_font('Get a daily coin bonus')}\n"
        f"  `•` /dig - {apply_font('Dig for coins every 10 mins')}\n"
        f"  `•` /gift - {apply_font('Gift a character to another user')}\n"
        f"  `•` /check [id] - {apply_font('Check a character details')}\n"
        f"  `•` /rarities - {apply_font('See all available rarities')}\n"
        f"  `•` /ping - {apply_font('Check bot latency')}\n"
        f"  `•` /sredeem [code] - {apply_font('Redeem a character code')}\n"
        f"  `•` /credeem [code] - {apply_font('Redeem a coin code')}\n"
        f"  `•` /shop - {apply_font('Buy a random character (up to 3 times a day)')}\n"
        f"  `•` /slot - {apply_font('Get a random amount of coins (24h cooldown)')}\n"
        f"  `•` /profile - {apply_font('See your profile')}\n"
    )

    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data="start_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            await query.message.reply_text(help_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# /rcode command (Sudo Only)
async def rcode(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if len(context.args) < 2:
        await update.message.reply_text(apply_font("❌ Usage: `/rcode [character id] [quantity]`"))
        return

    try:
        char_id = int(context.args[0])
        quantity = int(context.args[1])
        if quantity <= 0:
            await update.message.reply_text(apply_font("❌ Quantity must be a positive integer."))
            return
    except (ValueError, IndexError):
        await update.message.reply_text(apply_font("❌ Invalid arguments. Please provide a valid character ID and quantity."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM characters WHERE character_id = ?", (char_id,))
        char_name = cursor.fetchone()
        if not char_name:
            await update.message.reply_text(apply_font(f"❌ Character with ID `{char_id}` not found."))
            return

        redeem_code = generate_code()

        cursor.execute(
            "INSERT INTO character_redeem_codes (code, character_id, quantity) VALUES (?, ?, ?)",
            (redeem_code, char_id, quantity)
        )
        conn.commit()
        await update.message.reply_text(
            f"{apply_font('🎁 Character Redeem Code Generated:')}\n\n`{redeem_code}`\n\n" + 
            f"{apply_font('Character:')} {char_name[0]}\n" + 
            f"{apply_font('Quantity:')} {quantity}"
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text(apply_font("⚠️ A collision occurred, please try again."))
        conn.rollback()
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# /sredeem command
async def sredeem(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)

    if len(context.args) < 1:
        await update.message.reply_text(apply_font("❌ Usage: `/sredeem [code]`"))
        return

    redeem_code = context.args[0].upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT character_id, quantity FROM character_redeem_codes WHERE code = ?", (redeem_code,))
        code_info = cursor.fetchone()

        if not code_info:
            await update.message.reply_text(apply_font("❌ Invalid or expired character redeem code."))
            return

        char_id, quantity = code_info

        cursor.execute("SELECT COUNT(*) FROM claimed_codes WHERE user_id = ? AND code = ?", (user_id, redeem_code))
        if cursor.fetchone()[0] > 0:
            await update.message.reply_text(apply_font("❌ You have already claimed this code."))
            return

        cursor.execute(
            "SELECT T1.name, T1.file_id, T1.is_video, T1.rarity, T1.anime_name, T2.emoji FROM characters T1 INNER JOIN rarities T2 ON T1.rarity = T2.name WHERE T1.character_id = ?",
            (char_id,)
        )
        char_info = cursor.fetchone()
        if not char_info:
            await update.message.reply_text(apply_font("❌ Character not found. Code is invalid."))
            return

        char_name, file_id, is_video, rarity_name, anime_name, rarity_emoji = char_info

        # Update user's harem
        cursor.execute(
            "INSERT OR IGNORE INTO user_harem (user_id, character_id, grab_count) VALUES (?, ?, 0)",
            (user_id, char_id)
        )
        cursor.execute(
            "UPDATE user_harem SET grab_count = grab_count + 1 WHERE user_id = ? AND character_id = ?",
            (user_id, char_id)
        )

        # Update user's leaderboard score
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username, score) VALUES (?, ?, 0)", 
            (user_id, username)
        )
        cursor.execute(
            "UPDATE leaderboard SET score = score + 1, username = ?, last_updated = ? WHERE user_id = ?",
            (username, int(time.time()), user_id)
        )

        # Record that the user has claimed this code
        cursor.execute(
            "INSERT INTO claimed_codes (user_id, code) VALUES (?, ?)",
            (user_id, redeem_code)
        )

        # Decrement quantity and remove if 0
        new_quantity = quantity - 1
        if new_quantity > 0:
            cursor.execute(
                "UPDATE character_redeem_codes SET quantity = ? WHERE code = ?",
                (new_quantity, redeem_code)
            )
        else:
            cursor.execute("DELETE FROM character_redeem_codes WHERE code = ?", (redeem_code,))

        conn.commit()

        # Fix: separate font from markdown
        caption = (
            f"🎉 **[{username}](tg://user?id={user_id})**{apply_font(' successfully redeemed a code!')} 🎉\n\n"
            f"{apply_font('You got:')} {apply_font(char_name)}\n"
            f"{apply_font('Rarity:')} {rarity_name} {rarity_emoji}\n"
            f"{apply_font('From:')} {apply_font(anime_name)}\n"
            f"{apply_font('Id:')} {char_id}"
        )

        try:
            if is_video:
                await update.message.reply_video(video=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_photo(photo=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            await update.message.reply_text(caption, parse_mode=ParseMode.MARKDOWN)

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# /ccode command (Sudo Only)
async def ccode(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if len(context.args) < 2:
        await update.message.reply_text(apply_font("❌ Usage: `/ccode [coins amount] [quantity]`"))
        return

    try:
        coins_amount = int(context.args[0])
        quantity = int(context.args[1])
        if coins_amount <= 0 or quantity <= 0:
            await update.message.reply_text(apply_font("❌ Coins and quantity must be positive integers."))
            return
    except (ValueError, IndexError):
        await update.message.reply_text(apply_font("❌ Invalid arguments. Please provide a valid coins amount and quantity."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        redeem_code = generate_code()
        cursor.execute(
            "INSERT INTO coin_redeem_codes (code, coins, quantity) VALUES (?, ?, ?)",
            (redeem_code, coins_amount, quantity)
        )
        conn.commit()
        await update.message.reply_text(
            f"{apply_font('💰 Coin Redeem Code Generated:')}\n\n`{redeem_code}`\n\n" + 
            f"{apply_font('Coins:')} {coins_amount}\n" + 
            f"{apply_font('Quantity:')} {quantity}"
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text(apply_font("⚠️ A collision occurred, please try again."))
        conn.rollback()
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# /credeem command
async def credeem(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)

    if len(context.args) < 1:
        await update.message.reply_text(apply_font("❌ Usage: `/credeem [code]`"))
        return

    redeem_code = context.args[0].upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT coins, quantity FROM coin_redeem_codes WHERE code = ?", (redeem_code,))
        code_info = cursor.fetchone()

        if not code_info:
            await update.message.reply_text(apply_font("❌ Invalid or expired coin redeem code."))
            return

        coins, quantity = code_info

        cursor.execute("SELECT COUNT(*) FROM claimed_codes WHERE user_id = ? AND code = ?", (user_id, redeem_code))
        if cursor.fetchone()[0] > 0:
            await update.message.reply_text(apply_font("❌ You have already claimed this code."))
            return

        # Update user's coins
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username, coins) VALUES (?, ?, 0)", 
            (user_id, username)
        )
        cursor.execute(
            "UPDATE leaderboard SET coins = coins + ?, username = ?, last_updated = ? WHERE user_id = ?",
            (coins, username, int(time.time()), user_id)
        )

        # Record that the user has claimed this code
        cursor.execute(
            "INSERT INTO claimed_codes (user_id, code) VALUES (?, ?)",
            (user_id, redeem_code)
        )

        # Decrement quantity and remove if 0
        new_quantity = quantity - 1
        if new_quantity > 0:
            cursor.execute(
                "UPDATE coin_redeem_codes SET quantity = ? WHERE code = ?",
                (new_quantity, redeem_code)
            )
        else:
            cursor.execute("DELETE FROM coin_redeem_codes WHERE code = ?", (redeem_code,))

        conn.commit()

        await update.message.reply_text(
            f"🎉 {apply_font(f'{username} successfully redeemed a code!')}\n\n" +
            f"{apply_font(f'You got {coins} coins!')} 💰"
        )

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# /remove command (Sudo or Limited Sudo Only)
async def remove_character(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM limited_sudo WHERE user_id = ?", (user_id,))
        is_limited_sudo = cursor.fetchone()[0] > 0
    finally:
        conn.close()

    if not (is_sudo(user_id) or is_limited_sudo):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(apply_font("❌ Usage: `/remove [id]`"))
        return

    char_id = int(context.args[0])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM characters WHERE character_id = ?", (char_id,))
        char_name_row = cursor.fetchone()

        if not char_name_row:
            await update.message.reply_text(apply_font(f"❌ Character with ID `{char_id}` not found."))
            return

        char_name = char_name_row[0]

        cursor.execute("DELETE FROM characters WHERE character_id = ?", (char_id,))
        cursor.execute("DELETE FROM user_harem WHERE character_id = ?", (char_id,))
        cursor.execute("DELETE FROM character_redeem_codes WHERE character_id = ?", (char_id,))

        conn.commit()

        await update.message.reply_text(
            apply_font(f"✅ Character `{char_name}` ({char_id}) has been removed from the bot and all harems.")
        )
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# /bal or /balance command
async def get_balance(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username, coins) VALUES (?, ?, 0)",
            (user_id, username)
        )
        cursor.execute(
            "SELECT coins FROM leaderboard WHERE user_id = ?",
            (user_id,)
        )
        coins_amount = cursor.fetchone()[0]
        conn.commit()
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
        return
    finally:
        conn.close()

    await update.message.reply_text(
        f"💰 {apply_font(f'{username}, your current coin balance is')} {coins_amount}."
    )

async def give_coins(update: Update, context: CallbackContext):
    sender = update.effective_user
    sender_id = sender.id
    sender_username = get_user_display_name(sender)

    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(apply_font("❌ This command only works in groups."))
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(apply_font("❌ Please reply to the user you want to give coins to."))
        return

    recipient = update.message.reply_to_message.from_user
    recipient_id = recipient.id
    recipient_username = get_user_display_name(recipient)

    if sender_id == recipient_id:
        await update.message.reply_text(apply_font("❌ You can't give coins to yourself."))
        return

    if recipient.is_bot:
        await update.message.reply_text(apply_font("❌ You cannot give coins to a bot."))
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(apply_font("❌ Please provide a valid coin amount (1-500). E.g., `/give 100`"))
        return

    try:
        coins_amount = int(context.args[0])
        if not 1 <= coins_amount <= 500:
            await update.message.reply_text(apply_font("❌ You can only give between 1 and 500 coins."))
            return
    except ValueError:
        await update.message.reply_text(apply_font("❌ Please provide a valid number."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check sender's coin balance
        cursor.execute("SELECT coins FROM leaderboard WHERE user_id = ?", (sender_id,))
        sender_coins_info = cursor.fetchone()

        if not sender_coins_info or sender_coins_info[0] < coins_amount:
            await update.message.reply_text(apply_font("❌ You don't have enough coins."))
            return

        # Deduct coins from sender
        cursor.execute(
            "UPDATE leaderboard SET coins = coins - ?, username = ?, last_updated = ? WHERE user_id = ?",
            (coins_amount, sender_username, int(time.time()), sender_id)
        )

        # Add coins to recipient
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username, coins) VALUES (?, ?, 0)",
            (recipient_id, recipient_username)
        )
        cursor.execute(
            "UPDATE leaderboard SET coins = coins + ?, username = ?, last_updated = ? WHERE user_id = ?",
            (coins_amount, recipient_username, int(time.time()), recipient_id)
        )

        conn.commit()

        await update.message.reply_text(
            f"💰 {apply_font(f'{sender_username} has given {coins_amount} coins to {recipient_username}!')}"
        )

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# /supportgroup command (Sudo Only)
async def set_support_group(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text(apply_font("❌ Usage: `/supportgroup [group link]`"))
        return

    group_link = context.args[0]

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR REPLACE INTO bot_settings (setting_name, setting_value) VALUES (?, ?)",
            ('support_group_link', group_link)
        )
        conn.commit()
        await update.message.reply_text(apply_font(f"✅ Support group link successfully set to `{group_link}`."))
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# /givesudo command (Only for the main owner)
async def givesudo(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ Only the bot owner can use this command."))
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(apply_font("❌ Please reply to the user you want to give sudo to."))
        return

    user_to_give_sudo = update.message.reply_to_message.from_user
    new_sudo_id = user_to_give_sudo.id
    new_sudo_username = get_user_display_name(user_to_give_sudo)

    if new_sudo_id == SUDO_ID:
        await update.message.reply_text(apply_font("❌ You can't give sudo to yourself."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id FROM limited_sudo WHERE user_id = ?", (new_sudo_id,))
        if cursor.fetchone():
            await update.message.reply_text(apply_font(f"⚠️ {new_sudo_username} already has sudo permissions."))
            return

        cursor.execute("INSERT INTO limited_sudo (user_id) VALUES (?)", (new_sudo_id,))
        conn.commit()
        await update.message.reply_text(apply_font(f"✅ {new_sudo_username} has been given sudo permissions to use the `/upload` and `/remove` commands."))
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# --- New Command Handler: /resetdata ---
async def reset_data(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if len(context.args) < 1:
        await update.message.reply_text(apply_font("❌ Usage: `/resetdata [user_id]`"))
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(apply_font("❌ Invalid user ID. Please provide a number."))
        return

    if target_user_id == SUDO_ID:
        await update.message.reply_text(apply_font("❌ You can't reset the data of the bot owner."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if user exists
        cursor.execute("SELECT username FROM leaderboard WHERE user_id = ?", (target_user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            await update.message.reply_text(apply_font(f"⚠️ User `{target_user_id}` does not have any data to reset."))
            return

        username_to_reset = user_row[0]

        # Delete user's records from tables
        cursor.execute("DELETE FROM leaderboard WHERE user_id = ?", (target_user_id,))
        cursor.execute("DELETE FROM user_harem WHERE user_id = ?", (target_user_id,))

        conn.commit()
        # Fix: separate font from markdown
        await update.message.reply_text(
            f"{apply_font('✅ Data for')} [{username_to_reset}](tg://user?id={target_user_id}) {apply_font('has been successfully reset.')}",
            parse_mode=ParseMode.MARKDOWN
        )

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def start_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name = 'support_group_link'")
        support_link = cursor.fetchone()

        cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name = 'start_pic'")
        start_pic_file_id = cursor.fetchone()
    finally:
        conn.close()

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Me to Group", url=f"http://t.me/{context.bot.username}?startgroup=true")
        ],
        [
            InlineKeyboardButton("🔮 Developer", url=f"tg://user?id={SUDO_ID}")
        ]
    ]

    if support_link:
        keyboard[1].insert(0, InlineKeyboardButton("🌟 Support", url=support_link[0]))

    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━⧫\n"
        f"  ✦ {apply_font('Shota x Waifu Bot')} ✦\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━⧫\n"
        f"{apply_font('• I can help you find your waifu or husbando in your group chat.')}\n"
        f"{apply_font('• You can guess the character name using')} `/grab [name]` {apply_font('and add them to your collection.')}\n"
        f"{apply_font('• Use')} `/harem` {apply_font('to view your characters and')} `/leaderboard` {apply_font('to see the top collectors.')}\n"
        "\n"
        f"{apply_font('Tap on the buttons below for more info.')}"
    )

    try:
        if start_pic_file_id and (query.message.photo or query.message.video):
            await query.edit_message_media(
                media=InputMediaPhoto(media=start_pic_file_id[0], caption=welcome_message, parse_mode=ParseMode.MARKDOWN),
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            await query.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def spic(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    reply_message = update.message.reply_to_message
    if not reply_message or not reply_message.photo:
        await update.message.reply_text(apply_font("❌ Please reply to a photo to set it as the start pic."))
        return

    file_id = reply_message.photo[-1].file_id

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO bot_settings (setting_name, setting_value) VALUES (?, ?)",
            ('start_pic', file_id)
        )
        conn.commit()
        await update.message.reply_text(apply_font("✅ The start message picture has been updated."))
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def setpic(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    reply_message = update.message.reply_to_message
    if not reply_message or not reply_message.photo:
        await update.message.reply_text(apply_font("❌ Please reply to a photo to set it as the leaderboard pic."))
        return

    file_id = reply_message.photo[-1].file_id

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO bot_settings (setting_name, setting_value) VALUES (?, ?)",
            ('leaderboard_pic', file_id)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO bot_settings (setting_name, setting_value) VALUES (?, ?)",
            ('profile_pic', file_id)
        )
        conn.commit()
        await update.message.reply_text(apply_font("✅ The leaderboard and profile pictures have been updated."))
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# MODIFICATION: Changed leaderboard to show only users with a score > 0
async def leaderboard(update: Update, context: CallbackContext):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name = 'leaderboard_pic'")
        leaderboard_pic_file_id = cursor.fetchone()

        cursor.execute("SELECT user_id, username, score FROM leaderboard WHERE score > 0 ORDER BY score DESC LIMIT 10")
        top_players = cursor.fetchall()
    finally:
        conn.close()

    if not top_players:
        message = apply_font("No one has grabbed any characters yet! Be the first! 🧧")
    else:
        # Fix: Separate font from markdown
        message = f"{apply_font('🏮 TOP GRABBERS 🏮')}\n\n"
        for i, (user_id, username, score) in enumerate(top_players, 1):
            message += f" {i}. [{username}](tg://user?id={user_id}): {score} {apply_font('grabs')}\n"

    if leaderboard_pic_file_id:
        try:
            await update.message.reply_photo(
                photo=leaderboard_pic_file_id[0], 
                caption=message,
                parse_mode=ParseMode.MARKDOWN
            )
        except BadRequest:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def topcoins(update: Update, context: CallbackContext):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, username, coins FROM leaderboard ORDER BY coins DESC LIMIT 10")
        top_coin_hoarders = cursor.fetchall()
    finally:
        conn.close()

    if not top_coin_hoarders or all(coins == 0 for user_id, username, coins in top_coin_hoarders):
        await update.message.reply_text(apply_font("No one has earned any coins yet. Be the first! 💰"))
        return

    message = f"{apply_font('💰 TOP COIN HOARDERS 💰')}\n\n"
    for i, (user_id, username, coins) in enumerate(top_coin_hoarders, 1):
        message += f" {i}. [{username}](tg://user?id={user_id}): {coins} {apply_font('coins')}\n"

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def forced_drop(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    chat_id = update.effective_chat.id

    message_counters[chat_id] = 0

    await update.message.reply_text(apply_font("✨ A character will be forced to spawn shortly!"))
    await asyncio.sleep(1) 

    await drop_character(context, chat_id, is_forced=True)

# --- NEW HELPER FUNCTION FOR GRAB LOGIC ---
def is_valid_grab(user_guess: str, correct_name: str) -> bool:
    """
    Checks if the user's guess is a valid full-word match for the character's name.

    Args:
        user_guess: The user's input string.
        correct_name: The correct character's full name.

    Returns:
        True if the user's guess is a valid match, False otherwise.
    """
    # Fix: Normalize both the user guess and the correct name
    normalized_user_guess = normalize_name_for_match(user_guess)
    normalized_correct_name = normalize_name_for_match(correct_name)

    correct_words = set(normalized_correct_name.split())
    user_words = set(normalized_user_guess.split())

    if not user_words:
        return False

    # Check if all words in the user's guess are present in the correct name's words
    if user_words.issubset(correct_words):
        if any(len(word) > 1 for word in user_words):
            return True

    return False

async def grab_character(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)

    if chat_id not in spawned_characters:
        await update.message.reply_text(apply_font("❌ No character has spawned yet."))
        return

    correct_name_info = spawned_characters.get(chat_id)
    if not correct_name_info:
        await update.message.reply_text(apply_font("❌ The character has already been grabbed or disappeared."))
        return

    correct_name, rarity, char_id, anime_name = correct_name_info

    user_grab_name = " ".join(context.args).strip()

    if not user_grab_name:
        await update.message.reply_text(apply_font("❌ Please provide a character's name."))
        return

    if is_valid_grab(user_grab_name, correct_name):

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT OR IGNORE INTO leaderboard (user_id, username, score) VALUES (?, ?, 0)", 
                (user_id, username)
            )

            coins_earned = random.randint(1, 100)

            cursor.execute(
                "UPDATE leaderboard SET score = score + 1, coins = coins + ?, username = ?, last_updated = ? WHERE user_id = ?", 
                (coins_earned, username, int(time.time()), user_id)
            )

            cursor.execute("SELECT character_id FROM characters WHERE name = ?", (correct_name,))
            char_id_result = cursor.fetchone()

            if char_id_result:
                char_id = char_id_result[0]
                cursor.execute(
                    "INSERT OR IGNORE INTO user_harem (user_id, character_id, grab_count) VALUES (?, ?, 0)",
                    (user_id, char_id)
                )
                cursor.execute(
                    "UPDATE user_harem SET grab_count = grab_count + 1 WHERE user_id = ? AND character_id = ?",
                    (user_id, char_id)
                )

            conn.commit()
            del spawned_characters[chat_id]

            # Fetch rarity emoji for the message
            cursor.execute("SELECT emoji FROM rarities WHERE name = ?", (rarity,))
            rarity_emoji = cursor.fetchone()[0]

            # FIX: Separate font from markdown and construct the user mention correctly
            message = (
                f"🎉 **[{update.effective_user.first_name}](tg://user?id={user_id})**{apply_font('! You grabbed a (')}{rarity}{apply_font(') character!')} ✨\n\n"
                f"{apply_font('Name:')} {apply_font(correct_name)}\n"
                f"{apply_font('Id:')} {char_id}\n"
                f"{apply_font('Rarity:')} {rarity} {rarity_emoji}\n"
                f"{apply_font('From:')} {apply_font(anime_name)}\n\n"
                f"{apply_font(f'You also earned {coins_earned} coins!')} 💰"
            )

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

        except sqlite3.Error as e:
            await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
            conn.rollback()
        finally:
            conn.close()
    else:
        await update.message.reply_text(apply_font("❌ Incorrect name. Try again!"))

# --- Modified /upload command to show uploader's name ---
async def upload_character(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    uploader_name = get_user_display_name(update.effective_user)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM limited_sudo WHERE user_id = ?", (user_id,))
        is_limited_sudo = cursor.fetchone()[0] > 0
    finally:
        conn.close()

    if not (is_sudo(user_id) or is_limited_sudo):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    reply_message = update.message.reply_to_message
    if not reply_message or not (reply_message.photo or reply_message.video):
        await update.message.reply_text(
            apply_font("❌ To upload a character, reply to a photo or video with: `/upload name | rarity | id | anime`")
        )
        return

    args_str = " ".join(context.args).strip()
    parts = [s.strip() for s in args_str.split('|')]

    if len(parts) != 4:
        await update.message.reply_text(
            apply_font("❌ Please format the command correctly: `/upload [name] | [rarity] | [id] | [anime]`")
        )
        return

    character_name, rarity_name, character_id_str, anime_name = parts

    try:
        character_id = int(character_id_str)
    except ValueError:
        await update.message.reply_text(apply_font("❌ Character ID must be a number."))
        return

    file_id = reply_message.photo[-1].file_id if reply_message.photo else reply_message.video.file_id
    is_video = 1 if reply_message.video else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM rarities WHERE name = ?", (rarity_name,))
        if cursor.fetchone() is None:
            await update.message.reply_text(
                apply_font(f"❌ Rarity '{rarity_name}' does not exist. Please add it with `/addrarity` first.")
            )
            return

        cursor.execute(
            "INSERT INTO characters (character_id, name, file_id, rarity, anime_name, is_video, uploaded_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (character_id, character_name, file_id, rarity_name, anime_name, is_video, str(update.effective_user.id))
        )
        conn.commit()
        await update.message.reply_text(
            apply_font(f"✅ Character {character_name} from {anime_name} with rarity '{rarity_name}' (ID: {character_id}) successfully uploaded!")
        )

        cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name = 'upload_channel'")
        channel_id_row = cursor.fetchone()
        if channel_id_row:
            channel_id = channel_id_row[0]
            rarity_emoji = cursor.execute("SELECT emoji FROM rarities WHERE name = ?", (rarity_name,)).fetchone()[0]

            # Fix: Separate font from markdown
            caption = (
                f"{apply_font('New Character Uploaded')} ✨\n\n"
                f"{apply_font('Name:')} {apply_font(character_name)}\n"
                f"{apply_font('Anime:')} {apply_font(anime_name)}\n"
                f"{apply_font('Rarity:')} {rarity_name} {rarity_emoji}\n"
                f"{apply_font('ID:')} {character_id}\n"
                f"{apply_font('Uploaded by:')} {apply_font(uploader_name)}"
            )

            try:
                if is_video:
                    await context.bot.send_video(
                        chat_id=channel_id,
                        video=file_id,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=file_id,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                await update.message.reply_text(apply_font("✅ Character also sent to the upload channel."))
            except Forbidden:
                await update.message.reply_text(apply_font("❌ Failed to send to the channel. Please make sure I'm an admin there."))
            except Exception as e:
                logging.error(f"Failed to send to upload channel: {e}")
                await update.message.reply_text(apply_font("❌ Failed to send to the upload channel due to an error."))

    except sqlite3.IntegrityError:
        await update.message.reply_text(apply_font(f"⚠️ A character with the ID {character_id} already exists!"))
        conn.rollback()
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def sclaim(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)
    current_time = int(time.time())

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username) VALUES (?, ?)", 
            (user_id, username)
        )
        cursor.execute(
            "SELECT last_daily_claim FROM leaderboard WHERE user_id = ?",
            (user_id,)
        )
        last_claim_time = cursor.fetchone()[0]

        if current_time - last_claim_time < DAILY_COOLDOWN:
            remaining_time = DAILY_COOLDOWN - (current_time - last_claim_time)
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            seconds = int(remaining_time % 60)

            await update.message.reply_text(
                apply_font(f"⏳ You have already claimed your daily character. Please wait {hours}h {minutes}m {seconds}s.")
            )
            return

        selected_character_info = await select_character_by_rarity()

        if not selected_character_info:
            await update.message.reply_text(
                apply_font("❌ There are no characters available for your daily claim. A sudo user must upload some first.")
            )
            return

        name, file_id, rarity_name, emoji, char_id, is_video, anime_name, shop_price = selected_character_info

        coins_earned = random.randint(1, 100)

        cursor.execute(
            "UPDATE leaderboard SET last_daily_claim = ?, username = ?, last_updated = ?, score = score + 1, coins = coins + ? WHERE user_id = ?",
            (current_time, username, int(time.time()), coins_earned, user_id)
        )

        cursor.execute(
            "INSERT OR IGNORE INTO user_harem (user_id, character_id, grab_count) VALUES (?, ?, 0)",
            (user_id, char_id)
        )
        cursor.execute(
            "UPDATE user_harem SET grab_count = grab_count + 1 WHERE user_id = ? AND character_id = ?",
            (user_id, char_id)
        )

        conn.commit()

        # Fix: Separate font from markdown
        caption = (
            f"🎉 **[{username}](tg://user?id={user_id})**{apply_font(' claimed a daily character!')} 🎉\n\n"
            f"{apply_font('Name:')} {apply_font(name)}\n"
            f"{apply_font('Anime:')} {apply_font(anime_name)}\n"
            f"{apply_font('Rarity:')} {rarity_name} {emoji}\n"
            f"{apply_font('Coins Earned:')} {coins_earned}"
        )

        try:
            if is_video:
                await update.message.reply_video(video=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_photo(photo=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            await update.message.reply_text(caption, parse_mode=ParseMode.MARKDOWN)
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def bonus(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)
    current_time = int(time.time())

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        cursor.execute(
            "SELECT last_daily_bonus FROM leaderboard WHERE user_id = ?",
            (user_id,)
        )
        last_bonus_time = cursor.fetchone()[0]

        if current_time - last_bonus_time < DAILY_COOLDOWN:
            remaining_time = DAILY_COOLDOWN - (current_time - last_bonus_time)
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            seconds = int(remaining_time % 60)
            await update.message.reply_text(
                apply_font(f"⏳ You have already claimed your daily bonus. Please wait {hours}h {minutes}m {seconds}s.")
            )
            return

        bonus_amount = 300
        cursor.execute(
            "UPDATE leaderboard SET coins = coins + ?, last_daily_bonus = ?, username = ?, last_updated = ? WHERE user_id = ?",
            (bonus_amount, current_time, username, int(time.time()), user_id)
        )
        conn.commit()

        await update.message.reply_text(
            f"🎉 {apply_font(f'{username}, they have claimed their daily bonus of {bonus_amount} coins!')}",
            parse_mode=ParseMode.MARKDOWN
        )

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def dig(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)
    current_time = int(time.time())

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        cursor.execute(
            "SELECT last_dig_claim FROM leaderboard WHERE user_id = ?",
            (user_id,)
        )
        last_dig_time = cursor.fetchone()[0]

        if current_time - last_dig_time < DIG_COOLDOWN:
            remaining_time = DIG_COOLDOWN - (current_time - last_dig_time)
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            await update.message.reply_text(
                apply_font(f"⏳ You can only dig every 10 minutes. Please wait {minutes}m {seconds}s.")
            )
            return

        coin_change = random.randint(1, 50)
        is_gain = random.choice([True, False])

        if is_gain:
            cursor.execute(
                "UPDATE leaderboard SET coins = coins + ?, last_dig_claim = ?, username = ?, last_updated = ? WHERE user_id = ?",
                (coin_change, current_time, username, int(time.time()), user_id)
            )
            await update.message.reply_text(
                f"⛏️ {apply_font(f'{username} dug up {coin_change} coins!')}"
            )
        else:
            cursor.execute(
                "UPDATE leaderboard SET coins = MAX(0, coins - ?), last_dig_claim = ?, username = ?, last_updated = ? WHERE user_id = ?",
                (coin_change, current_time, username, int(time.time()), user_id)
            )
            await update.message.reply_text(
                f"🕳️ {apply_font(f'{username} fell into a pit and lost {coin_change} coins!')}"
            )

        conn.commit()

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# --- MODIFIED: Single /slot command handler ---
async def slot(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)
    current_time = int(time.time())

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        cursor.execute(
            f"SELECT last_slot_claim FROM leaderboard WHERE user_id = ?",
            (user_id,)
        )
        last_claim_time = cursor.fetchone()[0]

        if current_time - last_claim_time < DAILY_COOLDOWN:
            remaining_time = DAILY_COOLDOWN - (current_time - last_claim_time)
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            seconds = int(remaining_time % 60)
            await update.message.reply_text(
                apply_font(f"⏳ You have already used your roulette. Please wait {hours}h {minutes}m {seconds}s.")
            )
            return

        is_win = random.choice([True, False])
        if is_win:
            coins_won = random.randint(1, 200)
            cursor.execute(
                f"UPDATE leaderboard SET coins = coins + ?, last_slot_claim = ?, username = ?, last_updated = ? WHERE user_id = ?",
                (coins_won, current_time, username, int(time.time()), user_id)
            )
            # Fix: separate font from markdown
            await update.message.reply_text(
                f"🎰 {apply_font(f'{username} you got a roulette and won {coins_won} coins!')} 💰",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            coins_lost = random.randint(1, 200)
            cursor.execute(
                f"UPDATE leaderboard SET coins = MAX(0, coins - ?), last_slot_claim = ?, username = ?, last_updated = ? WHERE user_id = ?",
                (coins_lost, current_time, username, int(time.time()), user_id)
            )
            # Fix: separate font from markdown
            await update.message.reply_text(
                f"🎲 {apply_font(f'{username} lost the roulette and had to pay {coins_lost} coins!')} 💸",
                parse_mode=ParseMode.MARKDOWN
            )

        conn.commit()

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def shop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)
    current_time = int(time.time())

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username, shop_uses, last_shop_reset) VALUES (?, ?, 0, 0)",
            (user_id, username)
        )
        cursor.execute(
            "SELECT shop_uses, last_shop_reset, coins FROM leaderboard WHERE user_id = ?",
            (user_id,)
        )
        user_info = cursor.fetchone()
        shop_uses, last_shop_reset, user_coins = user_info

        # Reset shop uses if the cooldown has passed
        if current_time - last_shop_reset >= SHOP_COOLDOWN:
            shop_uses = 0
            cursor.execute("UPDATE leaderboard SET shop_uses = ?, last_shop_reset = ? WHERE user_id = ?", (shop_uses, current_time, user_id))
            conn.commit()

        # Check if the user has reached the daily limit
        if shop_uses >= SHOP_LIMIT:
            remaining_time = SHOP_COOLDOWN - (current_time - last_shop_reset)
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            seconds = int(remaining_time % 60)
            await update.message.reply_text(
                apply_font(f"❌ You have reached the daily limit for the shop. Please wait {hours}h {minutes}m {seconds}s.")
            )
            return

        selected_character_info = await select_character_by_rarity()

        if not selected_character_info:
            await update.message.reply_text(
                apply_font("❌ There are no characters available in the shop. A sudo user must upload some first.")
            )
            return

        name, file_id, rarity_name, emoji, char_id, is_video, anime_name, shop_cost = selected_character_info

        # Fix: separate font from markdown
        message = (
            f"✨ {apply_font('Available in the shop!')} ✨\n\n"
            f"{apply_font('Name:')} {apply_font(name)}\n"
            f"{apply_font('Anime:')} {apply_font(anime_name)}\n"
            f"{apply_font('Rarity:')} {rarity_name} {emoji}\n"
        )

        keyboard = [
            [InlineKeyboardButton(apply_font(f"💵 Buy for {shop_cost} coins 💵"), callback_data=f"buy_{char_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            if is_video:
                msg = await update.message.reply_video(
                    video=file_id, 
                    caption=message, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                msg = await update.message.reply_photo(
                    photo=file_id, 
                    caption=message, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            user_message_ownership[msg.message_id] = user_id
        except BadRequest:
            msg = await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            user_message_ownership[msg.message_id] = user_id

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def buy_character_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    message_id = query.message.message_id

    # Check for message ownership
    if user_id != user_message_ownership.get(message_id):
        await query.answer(apply_font("❌ This is not your shop item. Get your own!"), show_alert=True)
        return

    try:
        char_id = int(query.data.split('_')[1])
    except (IndexError, ValueError):
        await query.edit_message_caption(caption=apply_font("❌ An error occurred. Please try the /shop command again."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get character info
        cursor.execute(
            "SELECT T1.name, T1.file_id, T1.is_video, T1.rarity, T1.anime_name, T2.emoji, T2.shop_price FROM characters T1 "
            "INNER JOIN rarities T2 ON T1.rarity = T2.name "
            "WHERE T1.character_id = ?",
            (char_id,)
        )
        char_info = cursor.fetchone()

        if not char_info:
            await query.edit_message_caption(caption=apply_font("❌ This character is no longer available."))
            return

        name, file_id, is_video, rarity_name, anime_name, emoji, shop_cost = char_info

        # Get user info and check for existence
        cursor.execute("SELECT coins, shop_uses, last_shop_reset, username FROM leaderboard WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()
        if not user_info:
            await query.edit_message_caption(caption=apply_font("❌ You don't have enough coins or your profile is missing."))
            return

        user_coins, shop_uses, last_shop_reset, username = user_info

        # Reset shop uses if the cooldown has passed
        current_time = int(time.time())
        if current_time - last_shop_reset >= SHOP_COOLDOWN:
            shop_uses = 0
            cursor.execute("UPDATE leaderboard SET shop_uses = ?, last_shop_reset = ? WHERE user_id = ?", (shop_uses, current_time, user_id))
            conn.commit()

        # Re-check for daily shop limit
        if shop_uses >= SHOP_LIMIT:
             remaining_time = SHOP_COOLDOWN - (current_time - last_shop_reset)
             hours = int(remaining_time // 3600)
             minutes = int((remaining_time % 3600) // 60)
             seconds = int(remaining_time % 60)
             await query.answer(apply_font(f"❌ You have reached the daily limit for the shop. Please wait {hours}h {minutes}m {seconds}s."), show_alert=True)
             return

        # Check for sufficient coins
        if user_coins < shop_cost:
            await query.edit_message_caption(caption=apply_font("❌ You don't have enough coins to buy this character."))
            return

        # Deduct coins and update records
        cursor.execute(
            "UPDATE leaderboard SET coins = coins - ?, username = ?, last_updated = ? WHERE user_id = ?",
            (shop_cost, username, int(time.time()), user_id)
        )

        cursor.execute(
            "INSERT OR IGNORE INTO user_harem (user_id, character_id, grab_count) VALUES (?, ?, 0)",
            (user_id, char_id)
        )

        cursor.execute(
            "UPDATE user_harem SET grab_count = grab_count + 1 WHERE user_id = ? AND character_id = ?",
            (user_id, char_id)
        )

        cursor.execute(
            "UPDATE leaderboard SET score = score + 1, shop_uses = shop_uses + 1 WHERE user_id = ?",
            (user_id,)
        )

        conn.commit()

        # Fix: separate font from markdown
        caption = (
            f"🎉 **[{query.from_user.first_name}](tg://user?id={user_id})**{apply_font(' bought a character from the shop!')} 🎉\n\n"
            f"{apply_font('Name:')} {apply_font(name)}\n"
            f"{apply_font('Anime:')} {apply_font(anime_name)}\n"
            f"{apply_font('Rarity:')} {rarity_name} {emoji}\n"
            f"{apply_font('ID:')} {char_id}"
        )

        try:
            if query.message.photo or query.message.video:
                await query.edit_message_caption(
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                await query.message.reply_text(caption, parse_mode=ParseMode.MARKDOWN)

    except sqlite3.Error as e:
        await query.edit_message_caption(caption=apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# MODIFICATION: Add a bit to the /gift command
async def gift_character(update: Update, context: CallbackContext):
    sender = update.effective_user
    sender_id = sender.id
    sender_username = get_user_display_name(sender)

    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(apply_font("❌ This command only works in groups."))
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(apply_font("❌ Please reply to the user you want to gift to."))
        return

    recipient = update.message.reply_to_message.from_user
    recipient_id = recipient.id
    recipient_username = get_user_display_name(recipient)

    if sender_id == recipient_id:
        await update.message.reply_text(apply_font("❌ You can't gift a character to yourself."))
        return

    if recipient.is_bot:
        await update.message.reply_text(apply_font("❌ You cannot gift to a bot."))
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(apply_font("❌ Please provide a valid character id. E.g., `/gift 123`"))
        return

    char_id = int(context.args[0])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT T1.name, T1.rarity, T1.anime_name, T1.file_id, T1.is_video, T2.emoji, T3.grab_count FROM characters T1 "
            "INNER JOIN rarities T2 ON T1.rarity = T2.name "
            "INNER JOIN user_harem T3 ON T1.character_id = T3.character_id "
            "WHERE T3.user_id = ? AND T3.character_id = ?",
            (sender_id, char_id)
        )
        char_info = cursor.fetchone()

        if not char_info:
            await update.message.reply_text(apply_font("❌ You do not own this character."))
            return

        char_name, rarity, anime_name, file_id, is_video, emoji, sender_grab_count = char_info

        if sender_grab_count > 1:
            cursor.execute(
                "UPDATE user_harem SET grab_count = grab_count - 1 WHERE user_id = ? AND character_id = ?",
                (sender_id, char_id)
            )
        else:
            cursor.execute(
                "DELETE FROM user_harem WHERE user_id = ? AND character_id = ?",
                (sender_id, char_id)
            )

        cursor.execute(
            "UPDATE leaderboard SET score = score - 1, username = ?, last_updated = ? WHERE user_id = ?",
            (sender_username, int(time.time()), sender_id)
        )

        cursor.execute(
            "INSERT OR IGNORE INTO user_harem (user_id, character_id, grab_count) VALUES (?, ?, 0)",
            (recipient_id, char_id)
        )
        cursor.execute(
            "UPDATE user_harem SET grab_count = grab_count + 1 WHERE user_id = ? AND character_id = ?",
            (recipient_id, char_id)
        )

        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username, score) VALUES (?, ?, 0)", 
            (recipient_id, recipient_username)
        )
        cursor.execute(
            "UPDATE leaderboard SET score = score + 1, username = ?, last_updated = ? WHERE user_id = ?",
            (recipient_username, int(time.time()), recipient_id)
        )

        conn.commit()

        message_caption = (
            f"🎁 **[{sender_username}](tg://user?id={sender_id})**{apply_font(' has gifted')} **[{char_name}](tg://user?id={char_id})** {apply_font('to')} **[{recipient_username}](tg://user?id={recipient_id})**{apply_font('!')}\n"
            f"{apply_font('Rarity:')} {rarity} {emoji}"
        )

        try:
            if is_video:
                await update.message.reply_video(
                    video=file_id,
                    caption=message_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_photo(
                    photo=file_id,
                    caption=message_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        except BadRequest:
            await update.message.reply_text(message_caption, parse_mode=ParseMode.MARKDOWN)

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def harem(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT T1.name, T1.character_id, T1.rarity, T1.anime_name, T2.grab_count, T3.emoji FROM characters T1 "
            "INNER JOIN user_harem T2 ON T1.character_id = T2.character_id "
            "INNER JOIN rarities T3 ON T1.rarity = T3.name "
            "WHERE T2.user_id = ? ORDER BY T1.rarity DESC, T1.name ASC", 
            (user_id,)
        )
        user_characters = cursor.fetchall()

        cursor.execute(
            "SELECT T1.file_id, T1.is_video FROM characters T1 "
            "INNER JOIN leaderboard T2 ON T1.character_id = T2.fav_char_id "
            "WHERE T2.user_id = ?",
            (user_id,)
        )
        fav_char_info = cursor.fetchone()
    finally:
        conn.close()

    if not user_characters:
        await update.message.reply_text(apply_font("Your harem is empty! Grab some characters to fill it up."))
        return

    total_characters = len(user_characters)
    total_pages = (total_characters + HAREM_PAGE_SIZE - 1) // HAREM_PAGE_SIZE

    message, reply_markup = await build_harem_message(get_user_display_name(update.effective_user), user_characters, 1, total_pages)

    if fav_char_info:
        fav_file_id, is_video = fav_char_info
        try:
            if is_video:
                msg = await update.message.reply_video(
                    video=fav_file_id, 
                    caption=message, 
                    reply_markup=reply_markup, 
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                msg = await update.message.reply_photo(
                    photo=fav_file_id, 
                    caption=message, 
                    reply_markup=reply_markup, 
                    parse_mode=ParseMode.MARKDOWN
                )
            user_message_ownership[msg.message_id] = user_id
        except BadRequest:
            msg = await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            user_message_ownership[msg.message_id] = user_id
    else:
        msg = await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        user_message_ownership[msg.message_id] = user_id

async def harem_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    message_id = query.message.message_id

    if user_id != user_message_ownership.get(message_id):
        await query.answer(apply_font("❌ This is not your harem. Get your own!"), show_alert=True)
        return

    try:
        data = query.data.split('_')
        current_page = int(data[1])
        action = data[2]

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT T1.name, T1.character_id, T1.rarity, T1.anime_name, T2.grab_count, T3.emoji FROM characters T1 "
                "INNER JOIN user_harem T2 ON T1.character_id = T2.character_id "
                "INNER JOIN rarities T3 ON T1.rarity = T3.name "
                "WHERE T2.user_id = ? ORDER BY T1.rarity DESC, T1.name ASC", 
                (user_id,)
            )
            user_characters = cursor.fetchall()

            cursor.execute(
                "SELECT T1.file_id, T1.is_video FROM characters T1 "
                "INNER JOIN leaderboard T2 ON T1.character_id = T2.fav_char_id "
                "WHERE T2.user_id = ?",
                (user_id,)
            )
            fav_char_info = cursor.fetchone()
        finally:
            conn.close()

        total_characters = len(user_characters)
        total_pages = (total_characters + HAREM_PAGE_SIZE - 1) // HAREM_PAGE_SIZE

        new_page = current_page
        if action == "next" and current_page < total_pages:
            new_page = current_page + 1
        elif action == "prev" and current_page > 1:
            new_page = current_page - 1

        message, reply_markup = await build_harem_message(get_user_display_name(query.from_user), user_characters, new_page, total_pages)

        try:
            if fav_char_info and (query.message.photo or query.message.video):
                await query.edit_message_caption(
                    caption=message, 
                    reply_markup=reply_markup, 
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    message, 
                    reply_markup=reply_markup, 
                    parse_mode=ParseMode.MARKDOWN
                )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                await query.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    except (IndexError, ValueError):
        await query.edit_message_text(apply_font("An error occurred. Please try the /harem command again."))

async def build_harem_message(username, user_characters, page, total_pages):
    offset = (page - 1) * HAREM_PAGE_SIZE
    page_characters = user_characters[offset:offset + HAREM_PAGE_SIZE]

    # Fix: separate font from markdown and the username
    harem_message = f"{apply_font(f'{username}’s Harem')} 👑\n\n"

    if not page_characters:
        harem_message += apply_font("This page is empty.")
    else:
        for name, char_id, rarity, anime_name, count, emoji in page_characters:
            harem_message += (
                f"• {apply_font(name)}\n"
                f"  {apply_font('Anime:')} {apply_font(anime_name)}\n"
                f"  {apply_font('Rarity:')} {rarity} {emoji}\n"
                f"  {apply_font('ID:')} {char_id}\n"
                f"  {apply_font('Grabs:')} x{count}\n\n"
            )

    harem_message += f"\n{apply_font('Page')} {page} {apply_font('of')} {total_pages}"

    keyboard = []
    row = []
    if page > 1:
        row.append(InlineKeyboardButton(apply_font("⬅️ Prev"), callback_data=f"harem_{page}_prev"))
    if page < total_pages:
        row.append(InlineKeyboardButton(apply_font("Next ➡️"), callback_data=f"harem_{page}_next"))
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    return harem_message, reply_markup

async def fav_character(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(apply_font("❌ Please provide a valid character ID. E.g., `/fav 123`"))
        return

    char_id = int(context.args[0])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM user_harem WHERE user_id = ? AND character_id = ?",
            (user_id, char_id)
        )
        is_owned = cursor.fetchone()[0]

        if not is_owned:
            await update.message.reply_text(apply_font("❌ You can only set a favorite character you own."))
            return

        cursor.execute(
            "UPDATE leaderboard SET fav_char_id = ? WHERE user_id = ?",
            (char_id, user_id)
        )
        conn.commit()

        await update.message.reply_text(apply_font("✅ Your favorite character has been set!"))

    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def rarities(update: Update, context: CallbackContext):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, emoji, spawn_weight, shop_price FROM rarities ORDER BY spawn_weight DESC")
        all_rarities = cursor.fetchall()
    finally:
        conn.close()

    if not all_rarities:
        await update.message.reply_text(apply_font("No rarities have been added yet. A sudo user can add them with `/addrarity`."))
        return

    message = f"{apply_font('✨ Available Rarities ✨')}\n\n"
    for name, emoji, weight, price in all_rarities:
        message += f"{name} {emoji}\n- {apply_font('Spawn Weight:')} {weight}\n"
        if price > 0:
            message += f"- {apply_font('Shop Price:')} {price} 💰\n"

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def set_droptime(update: Update, context: CallbackContext):
    global messages_until_drop
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(apply_font("❌ Please provide a valid number. E.g., `/droptime 100`"))
        return

    new_droptime = int(context.args[0])
    if not 1 <= new_droptime <= 1000:
        await update.message.reply_text(apply_font("❌ The number of messages must be between 1 and 1000."))
        return

    messages_until_drop = new_droptime
    await update.message.reply_text(apply_font(f"✅ Drop time has been updated to {messages_until_drop} messages!"))

    for chat_id in message_counters:
        message_counters[chat_id] = 0

async def add_rarity(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if len(context.args) < 4:
        await update.message.reply_text(apply_font("❌ Usage: /addrarity [name] [emoji] [spawn_weight] [shop_price]"))
        return

    rarity_name = context.args[0]
    emoji = context.args[1]

    try:
        spawn_weight = int(context.args[2])
        shop_price = int(context.args[3])
        if spawn_weight <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text(apply_font("❌ Spawn weight and shop price must be positive integers."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO rarities (name, emoji, spawn_weight, shop_price) VALUES (?, ?, ?, ?)", 
            (rarity_name, emoji, spawn_weight, shop_price)
        )
        conn.commit()
        await update.message.reply_text(
            apply_font(f"✅ Rarity '{rarity_name}' {emoji} added successfully with a spawn weight of {spawn_weight} and a shop price of {shop_price}.")
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text(apply_font("⚠️ A rarity with this name already exists."))
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

async def resetall(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)

    await update.message.reply_text(
        apply_font("🗑️ All bot data (characters, rarities, and leaderboard) has been cleared.")
    )

    setup_database()

async def ping(update: Update, context: CallbackContext):
    start_time = time.time()
    message = await update.message.reply_text(apply_font("Pinging..."))
    end_time = time.time()

    ping_ms = int((end_time - start_time) * 1000)

    ram_usage = psutil.virtual_memory().percent

    disk_usage = psutil.disk_usage('.').percent

    # Fix: separate font from markdown
    response = (
        f"{apply_font('Pong!')} 🏓\n"
        f"{apply_font('Ping:')} {ping_ms}ms\n"
        f"{apply_font('RAM:')} {ram_usage}%\n"
        f"{apply_font('Disk:')} {disk_usage}%"
    )

    await message.edit_text(response, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(apply_font("❌ Usage: `/check [id]`"))
        return

    char_id = int(context.args[0])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT T1.name, T1.rarity, T1.anime_name, T1.file_id, T2.emoji, T1.is_video FROM characters T1 "
            "INNER JOIN rarities T2 ON T1.rarity = T2.name "
            "WHERE T1.character_id = ?",
            (char_id,)
        )
        character_info = cursor.fetchone()

        if not character_info:
            await update.message.reply_text(apply_font("❌ Character not found."))
            return

        name, rarity, anime_name, file_id, emoji, is_video = character_info

        # Fix: Separate font from markdown
        message_text = (
            f"{apply_font('Character Details')} 🪭\n\n"
            f"{apply_font('Name:')} {apply_font(name)}\n"
            f"{apply_font('Anime:')} {apply_font(anime_name)}\n"
            f"{apply_font('Rarity:')} {rarity} {emoji}\n"
            f"{apply_font('ID:')} {char_id}"
        )

        keyboard = [
            [InlineKeyboardButton(apply_font("Top 10 Grabbers 🏆"), callback_data=f"top10_{char_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            if is_video:
                message = await update.message.reply_video(
                    video=file_id,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                message = await update.message.reply_photo(
                    photo=file_id,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            user_message_ownership[message.message_id] = user_id
        except BadRequest:
            message = await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            user_message_ownership[message.message_id] = user_id
    finally:
        conn.close()

async def top10_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    message_id = query.message.message_id

    if user_id != user_message_ownership.get(message_id):
        await query.answer(apply_font("❌ This is not your check. Get your own!"), show_alert=True)
        return

    try:
        char_id = int(query.data.split('_')[1])
    except (IndexError, ValueError):
        await query.edit_message_text(apply_font("An error occurred. Please try again."))
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name, is_video FROM characters WHERE character_id = ?", (char_id,))
        char_info_result = cursor.fetchone()
        if not char_info_result:
            await query.edit_message_caption(caption=apply_font("❌ Character not found."))
            return
        char_name, is_video = char_info_result

        cursor.execute(
            "SELECT T1.user_id, T1.username, T2.grab_count FROM leaderboard T1 "
            "INNER JOIN user_harem T2 ON T1.user_id = T2.user_id "
            "WHERE T2.character_id = ? ORDER BY T2.grab_count DESC LIMIT 10",
            (char_id,)
        )
        top_grabbers = cursor.fetchall()

        # Fix: Separate font from markdown
        message = f"🏆 {apply_font('Top Grabbers for')} {apply_font(char_name)} 🏆\n\n"
        if not top_grabbers:
            message += apply_font(f"No one has grabbed {char_name} yet.")
        else:
            for i, (grabber_user_id, username, count) in enumerate(top_grabbers, 1):
                message += f" {i}. [{username}](tg://user?id={grabber_user_id}): {count} {apply_font('grabs')}\n"

        try:
            if query.message.photo or query.message.video:
                await query.edit_message_caption(
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
        except BadRequest as e:
            logging.error(f"BadRequest in top10_callback: {e}")
            try:
                await query.message.reply_text(apply_font("An error occurred. The original message may have been deleted."))
            except Exception:
                pass
    finally:
        conn.close()

async def bcast(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(apply_font("❌ Reply to a message to broadcast it."))
        return

    broadcast_message = update.message.reply_to_message

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, type FROM broadcast_targets")
        targets = cursor.fetchall()
    finally:
        conn.close()

    success_count = 0
    fail_count = 0

    for target_id, target_type in targets:
        try:
            await context.bot.forward_message(chat_id=target_id, from_chat_id=update.effective_chat.id, message_id=broadcast_message.message_id)
            success_count += 1
            await asyncio.sleep(0.1)
        except Forbidden:
            fail_count += 1
            logging.info(f"Failed to broadcast to {target_type} {target_id}: Bot was blocked or removed.")
        except Exception as e:
            fail_count += 1
            logging.error(f"An error occurred while broadcasting to {target_type} {target_id}: {e}")

    if success_count > 0:
        await update.message.reply_text(apply_font(f"✅ {success_count} successful broadcasts done.\n❌ {fail_count} failed."))

async def set_channel(update: Update, context: CallbackContext):
    if not is_sudo(update.effective_user.id):
        await update.message.reply_text(apply_font("❌ You are not authorized to use this command."))
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text(apply_font("❌ Usage: `/setchannel [channel_id]`"))
        return

    channel_id = context.args[0]

    if not channel_id.startswith('@') and not channel_id.startswith('-100'):
        try:
            int(channel_id)
        except ValueError:
            await update.message.reply_text(apply_font("❌ Please provide a valid channel username (e.g., `@mychannel`) or ID (e.g., `-100...`)."))
            return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR REPLACE INTO bot_settings (setting_name, setting_value) VALUES (?, ?)", 
            ('upload_channel', channel_id)
        )
        conn.commit()
        await update.message.reply_text(apply_font(f"✅ Upload channel successfully set to `{channel_id}`. Make sure the bot is an admin there."))
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
    finally:
        conn.close()

# NEW COMMAND: /profile
async def profile(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        conn.commit()

        cursor.execute("SELECT score, coins FROM leaderboard WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        user_score = user_data[0]
        user_coins = user_data[1]

        cursor.execute("SELECT COUNT(*) FROM leaderboard WHERE score > ?", (user_score,))
        grab_rank = cursor.fetchone()[0] + 1

        cursor.execute("SELECT COUNT(*) FROM leaderboard WHERE coins > ?", (user_coins,))
        coin_rank = cursor.fetchone()[0] + 1
    except sqlite3.Error as e:
        await update.message.reply_text(apply_font(f"An internal error occurred: {e}"))
        conn.rollback()
        return
    finally:
        conn.close()

    # Fix: Separate font from markdown
    message = (
        f"{apply_font(f'{username}’s Profile')} 👑\n\n"
        f"{apply_font('Your Status:')}\n"
        f"• {apply_font('Total characters grabbed:')} {user_score}\n"
        f"• {apply_font('Grabbing Rank:')} {grab_rank} 🍃\n"
        f"• {apply_font('Total coins:')} {user_coins}\n"
        f"• {apply_font('Coin Rank:')} {coin_rank} 🧧"
    )

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = get_user_display_name(update.effective_user)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO leaderboard (user_id, username, group_id, last_updated) VALUES (?, ?, ?, ?)",
            (user_id, username, chat_id, int(time.time()))
        )
        cursor.execute(
            "UPDATE leaderboard SET username = ?, last_updated = ? WHERE user_id = ?",
            (username, int(time.time()), user_id)
        )

        if update.effective_chat.type in ["group", "supergroup"]:
            group_name = update.effective_chat.title
            cursor.execute(
                "INSERT OR IGNORE INTO groups (group_id, group_name) VALUES (?, ?)",
                (chat_id, group_name)
            )
            cursor.execute(
                "UPDATE groups SET group_name = ? WHERE group_id = ?",
                (group_name, chat_id)
            )

        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database error in handle_message: {e}")
        conn.rollback()
    finally:
        conn.close()

    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_group_members(context, chat_id):
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO broadcast_targets (id, type) VALUES (?, ?)", 
                (chat_id, 'group')
            )
            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database error updating broadcast targets: {e}")
            conn.rollback()
        finally:
            conn.close()

        if update.message.text or update.message.sticker:
            if not update.message.text or not update.message.text.startswith('/'):
                message_counters[chat_id] += 1

                if message_counters[chat_id] >= messages_until_drop:
                    message_counters[chat_id] = 0 
                    await drop_character(context, chat_id)

async def drop_character(context: CallbackContext, chat_id: int, is_forced=False):
    selected_character_info = await select_character_by_rarity()

    if not selected_character_info:
        await context.bot.send_message(
            chat_id=chat_id, 
            text=apply_font("No characters found to drop. A sudo user must upload some first.")
        )
        return

    name, file_id, rarity_name, emoji, char_id, is_video, anime_name, shop_price = selected_character_info

    # Fix: Separate font from markdown
    caption = f"{apply_font('A')} {rarity_name} {emoji} {apply_font('character has appeared! Type')} /grab {apply_font('name to claim them.')}"

    try:
        if is_video:
            await context.bot.send_video(
                chat_id=chat_id,
                video=file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )

        spawned_characters[chat_id] = (name, rarity_name, char_id, anime_name)

    except BadRequest as e:
        if "Wrong file identifier/http url specified" in str(e):
            logging.error(f"Invalid file_id for character '{name}'. Removing from database.")
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM characters WHERE name = ? AND rarity = ?", (name, rarity_name))
                conn.commit()
                await context.bot.send_message(chat_id=chat_id, text=apply_font("A character failed to drop. Trying another one!"))
                await drop_character(context, chat_id)
            except sqlite3.Error as db_e:
                logging.error(f"DB error while trying to clean up bad character: {db_e}")
                conn.rollback()
            finally:
                conn.close()
        else:
            logging.error(f"General BadRequest in drop_character: {e}")
            await context.bot.send_message(chat_id=chat_id, text=apply_font("An error occurred while dropping a character."))

async def select_character_by_rarity():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name, emoji, spawn_weight, shop_price FROM rarities")
        rarities_data = cursor.fetchall()

        if not rarities_data:
            return None

        rarity_names = [rarity[0] for rarity in rarities_data]
        spawn_weights = [rarity[2] for rarity in rarities_data]

        if not any(spawn_weights):
            return None

        selected_rarity_name = random.choices(rarity_names, weights=spawn_weights, k=1)[0]

        cursor.execute(
            "SELECT T1.name, T1.file_id, T2.name, T2.emoji, T1.character_id, T1.is_video, T1.anime_name, T2.shop_price FROM characters AS T1 "
            "INNER JOIN rarities AS T2 ON T1.rarity = T2.name "
            "WHERE T1.rarity = ? ORDER BY RANDOM() LIMIT 1", (selected_rarity_name,)
        )
        result = cursor.fetchone()

        if not result:
            cursor.execute(
                "SELECT T1.name, T1.file_id, T2.name, T2.emoji, T1.character_id, T1.is_video, T1.anime_name, T2.shop_price FROM characters AS T1 "
                "INNER JOIN rarities AS T2 ON T1.rarity = T2.name "
                "ORDER BY RANDOM() LIMIT 1"
            )
            result = cursor.fetchone()
            if not result:
                return None

        name, file_id, rarity_name, emoji, char_id, is_video, anime_name, shop_price = result
        return (name, file_id, rarity_name, emoji, char_id, is_video, anime_name, shop_price)
    finally:
        conn.close()

def main():
    setup_database()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(help_menu, pattern="^help_menu$"))
    application.add_handler(CallbackQueryHandler(start_menu, pattern="^start_menu$"))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("topcoins", topcoins))
    application.add_handler(CommandHandler("fdrop", forced_drop))
    application.add_handler(CommandHandler("grab", grab_character))
    application.add_handler(CommandHandler("upload", upload_character))
    application.add_handler(CommandHandler("sclaim", sclaim))
    application.add_handler(CommandHandler("bonus", bonus))
    application.add_handler(CommandHandler("dig", dig))
    application.add_handler(CommandHandler("harem", harem))
    application.add_handler(CallbackQueryHandler(harem_callback, pattern=r'^harem_'))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CallbackQueryHandler(top10_callback, pattern=r'^top10_'))
    application.add_handler(CommandHandler("rarities", rarities))
    application.add_handler(CommandHandler("droptime", set_droptime))
    application.add_handler(CommandHandler("addrarity", add_rarity))
    application.add_handler(CommandHandler("resetall", resetall))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("bcast", bcast))
    application.add_handler(CommandHandler("setchannel", set_channel))
    application.add_handler(CommandHandler("spic", spic))
    application.add_handler(CommandHandler("setpic", setpic))
    application.add_handler(CommandHandler("gift", gift_character))
    application.add_handler(CommandHandler("fav", fav_character))
    application.add_handler(CommandHandler("supportgroup", set_support_group))

    # New handlers
    application.add_handler(CommandHandler("givesudo", givesudo))
    application.add_handler(CommandHandler("rcode", rcode))
    application.add_handler(CommandHandler("sredeem", sredeem))
    application.add_handler(CommandHandler("ccode", ccode))
    application.add_handler(CommandHandler("credeem", credeem))
    application.add_handler(CommandHandler("give", give_coins))
    application.add_handler(CommandHandler("remove", remove_character))
    application.add_handler(CommandHandler(["bal", "balance"], get_balance))
    application.add_handler(CommandHandler("resetdata", reset_data))
    application.add_handler(CommandHandler("shop", shop))
    application.add_handler(CallbackQueryHandler(buy_character_callback, pattern=r'^buy_'))
    application.add_handler(CommandHandler("slot", slot))
    application.add_handler(CommandHandler("profile", profile))

    # The MessageHandler now listens for any message that is not a command, in a group or supergroup
    application.add_handler(MessageHandler(filters.ALL & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & (~filters.COMMAND), handle_message))

    print("Bot is starting...")
    application.run_polling()
    print("Bot is shutting down.")

if __name__ == '__main__':
    main()